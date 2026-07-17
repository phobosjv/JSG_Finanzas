"""
test_backup_full.py
===================
Tests del backup admin ampliado (admin_2, v1.22.0): el backup completo debe
servir para migrar un servidor 1:1. Verifica que el export incluye y el import
restaura:
  * app_config (nombre de app, umbral de polvo, secretos: email y VAPID)
  * tax_brackets (tramos IRPF, replace-all)
  * security_splits (por ticker, portable)
  * subcarteras (por usuario, posiciones por ticker)
  * campos extra de usuario (email/is_enabled/expires_at)
Y que un backup admin_1 (sin esas secciones) se sigue importando (retrocompat).
"""
import json

from app.models import AppConfig


def _sec(admin_client, ticker, market="ibex35"):
    return admin_client.post("/api/securities", json={
        "name": ticker, "yahoo_ticker": ticker, "market": market, "currency": "EUR",
    }).json()["id"]


def _seed_full_system(admin_client, db):
    """Crea un sistema con config, tramos, split, posición y subcartera."""
    # Configuración no sensible (vía endpoints).
    admin_client.patch("/api/admin/config/app-name", json={"app_name": "Mi Portafolio"})
    admin_client.patch("/api/admin/config/dust-threshold", json={"dust_threshold": "0.25"})

    # Secretos (vía BD directa: misma BD en memoria que el client, StaticPool).
    db.add(AppConfig(key="email_config", value=json.dumps({
        "provider": "gmail", "user": "admin@x.com", "password": "s3cr3t",
    })))
    db.add(AppConfig(key="vapid_private_key", value="PRIV-KEY-XYZ"))
    db.add(AppConfig(key="vapid_public_key", value="PUB-KEY-XYZ"))
    db.commit()

    # Tramo IRPF.
    admin_client.post("/api/admin/config/tax-brackets", json={
        "min_amount": "0", "max_amount": "6000", "rate": "19", "sort_order": 0,
    })

    # Valor + split.
    sec = _sec(admin_client, "SAN.MC")
    admin_client.post(f"/api/admin/securities/{sec}/splits", json={
        "ex_date": "2023-05-01", "ratio_num": 2, "ratio_den": 1, "notes": "split 2:1",
    })

    # Posición con una compra.
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-10", "shares": "100", "price": "3.5",
        "fee": "1", "currency": "EUR", "exchange_rate": "1",
    })

    # Subcartera con esa posición.
    sc = admin_client.post("/api/subcarteras", json={
        "name": "Bancos", "description": "Sector financiero",
    }).json()["id"]
    admin_client.post(f"/api/subcarteras/{sc}/positions/{pos}")
    return {"sec": sec, "pos": pos, "sc": sc}


# ---------------------------------------------------------------------------
#  Export: contenido de las secciones nuevas
# ---------------------------------------------------------------------------

def test_export_includes_config_brackets_splits_subcarteras(admin_client, db, seed_markets):
    _seed_full_system(admin_client, db)
    data = admin_client.get("/api/admin/backup/export").json()

    assert data["version"] == "admin_2"

    # app_config con nombre, umbral y secretos.
    cfg = {c["key"]: c["value"] for c in data["app_config"]}
    assert cfg["app_name"] == "Mi Portafolio"
    assert cfg["dust_threshold"] == "0.25"
    assert cfg["vapid_private_key"] == "PRIV-KEY-XYZ"
    assert "s3cr3t" in cfg["email_config"]   # secreto en claro (migración 1:1)

    # Tramos.
    assert len(data["tax_brackets"]) == 1
    assert float(data["tax_brackets"][0]["rate"]) == 19.0

    # Split referenciado por ticker.
    assert len(data["security_splits"]) == 1
    sp = data["security_splits"][0]
    assert sp["security_ticker"] == "SAN.MC"
    assert sp["ratio_num"] == 2 and sp["ratio_den"] == 1

    # Subcartera anidada en el usuario, posición por ticker.
    port = next(p for p in data["portfolios"] if p["username"] == "adminuser")
    assert len(port["subcarteras"]) == 1
    sub = port["subcarteras"][0]
    assert sub["name"] == "Bancos"
    assert sub["position_tickers"] == ["SAN.MC"]


def test_export_includes_user_fields(admin_client, db, seed_markets):
    _seed_full_system(admin_client, db)
    data = admin_client.get("/api/admin/backup/export").json()
    u = next(u for u in data["users"] if u["username"] == "adminuser")
    # Campos que faltaban en admin_1.
    for key in ("email", "is_enabled", "expires_at", "created_at", "last_login_at"):
        assert key in u
    assert u["is_enabled"] is True


# ---------------------------------------------------------------------------
#  Import: restaura / sobrescribe
# ---------------------------------------------------------------------------

def test_restore_reproduces_config_after_change(admin_client, db, seed_markets):
    _seed_full_system(admin_client, db)
    backup = admin_client.get("/api/admin/backup/export").json()

    # Alterar el sitio: cambiar nombre y añadir un tramo bogus.
    admin_client.patch("/api/admin/config/app-name", json={"app_name": "OTRO"})
    admin_client.post("/api/admin/config/tax-brackets", json={
        "min_amount": "6000", "max_amount": None, "rate": "99", "sort_order": 5,
    })

    r = admin_client.post("/api/admin/backup/import", json=backup)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["config_keys"] >= 5            # app_name, dust, email, 2×vapid
    assert res["tax_brackets_set"] == 1       # replace-all

    # Nombre restaurado (upsert de app_config).
    assert admin_client.get("/api/config").json()["app_name"] == "Mi Portafolio"
    # Tramos: replace-all deja solo el del backup (el bogus 99% desaparece).
    brackets = admin_client.get("/api/admin/config/tax-brackets").json()
    assert len(brackets) == 1
    assert float(brackets[0]["rate"]) == 19.0


def test_reimport_is_idempotent(admin_client, db, seed_markets):
    _seed_full_system(admin_client, db)
    backup = admin_client.get("/api/admin/backup/export").json()

    r1 = admin_client.post("/api/admin/backup/import", json=backup).json()
    r2 = admin_client.post("/api/admin/backup/import", json=backup).json()

    # Segunda pasada: no duplica movimientos, splits ni subcarteras.
    assert r2["transactions_added"] == 0
    assert r2["splits_added"] == 0            # ya existe (upsert por ex_date)
    assert r2["subcarteras_added"] == 0       # ya existe (upsert por nombre)
    # El split sigue siendo único.
    sec_id = _sec_id(admin_client, "SAN.MC")
    splits = admin_client.get(f"/api/admin/securities/{sec_id}/splits").json()
    assert len(splits) == 1


def test_import_updates_existing_user_fields(admin_client, db, test_user):
    # test_user ("testuser") existe con is_enabled=True y sin email.
    backup = {
        "version": "admin_2",
        "users": [{
            "username": "testuser", "password_hash": "x", "is_admin": False,
            "is_enabled": False, "email": "nuevo@x.com", "expires_at": None,
        }],
        "markets": [], "securities": [], "portfolios": [],
        "app_config": [], "tax_brackets": [], "security_splits": [],
    }
    r = admin_client.post("/api/admin/backup/import", json=backup)
    assert r.status_code == 200, r.text
    assert r.json()["users_updated"] == 1

    from app.models import User
    from sqlalchemy import select
    u = db.scalar(select(User).where(User.username == "testuser"))
    db.refresh(u)
    assert u.email == "nuevo@x.com"
    assert u.is_enabled is False


# ---------------------------------------------------------------------------
#  Retrocompatibilidad admin_1
# ---------------------------------------------------------------------------

def test_admin1_backup_still_imports(admin_client):
    payload = {
        "version": "admin_1",
        "markets": [], "users": [], "securities": [], "portfolios": [],
    }
    r = admin_client.post("/api/admin/backup/import", json=payload)
    assert r.status_code == 200, r.text
    res = r.json()
    # Sin secciones nuevas: cero cambios en config/tramos.
    assert res["config_keys"] == 0
    assert res["tax_brackets_set"] == 0
    assert res["splits_added"] == 0


def _sec_id(admin_client, ticker):
    return next(
        s["id"] for s in admin_client.get("/api/securities").json()
        if s["yahoo_ticker"] == ticker
    )
