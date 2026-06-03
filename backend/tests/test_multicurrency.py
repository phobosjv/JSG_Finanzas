"""
test_multicurrency.py
=====================
Tests del soporte multi-divisa (v1.8.0): tipos del BCE por divisa, valoración en
euros usando el tipo de la divisa del valor, y validación de divisas soportadas.
"""

from datetime import date, timedelta
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import EcbRate, PriceSnapshot
from app.providers.ecb import _parse_csv_multi
from app.scheduler import jobs


# ---------------------------------------------------------------------------
#  Parseo del CSV multi-divisa del BCE
# ---------------------------------------------------------------------------

def test_parse_csv_multi_divisas():
    csv = (
        "KEY,FREQ,CURRENCY,CURRENCY_DENOM,TIME_PERIOD,OBS_VALUE\n"
        "EXR.D.USD.EUR.SP00.A,D,USD,EUR,2024-01-10,1.1000\n"
        "EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,2024-01-10,0.8600\n"
        "EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,2024-01-10,160.50\n"
        "EXR.D.EUR.EUR.SP00.A,D,EUR,EUR,2024-01-10,1.0000\n"  # EUR base → se ignora
    )
    rates = _parse_csv_multi(csv)
    assert rates[("2024-01-10", "USD")] == D("1.1000")
    assert rates[("2024-01-10", "GBP")] == D("0.8600")
    assert rates[("2024-01-10", "JPY")] == D("160.50")
    assert ("2024-01-10", "EUR") not in rates


# ---------------------------------------------------------------------------
#  Divisa soportada: validación
# ---------------------------------------------------------------------------

def test_security_divisa_no_soportada_rechazada(admin_client, seed_markets):
    """Crear un valor en GBP sin haberla configurado como soportada → 422."""
    r = admin_client.post("/api/securities", json={
        "name": "Vodafone", "yahoo_ticker": "VOD.L", "market": "ibex35", "currency": "GBP",
    })
    assert r.status_code == 422


def test_configurar_divisa_y_crear_valor(admin_client, seed_markets):
    """Tras configurar GBP como soportada, se puede crear un valor en GBP."""
    admin_client.patch("/api/admin/config/currencies", json={"currencies": ["USD", "GBP"]})
    r = admin_client.post("/api/securities", json={
        "name": "Vodafone", "yahoo_ticker": "VOD.L", "market": "ibex35", "currency": "GBP",
    })
    assert r.status_code == 201, r.text
    assert r.json()["currency"] == "GBP"


# ---------------------------------------------------------------------------
#  Valoración en EUR con el tipo de la divisa del valor
# ---------------------------------------------------------------------------

def test_valoracion_usa_tipo_de_la_divisa(admin_client, seed_markets, engine):
    """
    Un valor en GBP se valora en EUR con el tipo GBP del BCE (no rate=1).
    10 part. × 6 GBP / 1.20 (GBP por EUR) = 50 €.
    """
    admin_client.patch("/api/admin/config/currencies", json={"currencies": ["USD", "GBP"]})
    sec = admin_client.post("/api/securities", json={
        "name": "GBP Co", "yahoo_ticker": "GBPCO.L", "market": "ibex35", "currency": "GBP",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-10", "shares": "10", "price": "5",
        "fee": "0", "currency": "GBP", "exchange_rate": "1.15",
    })

    with Session(engine) as s:
        s.add(EcbRate(date="2024-06-01", currency="GBP", rate=D("1.20")))
        s.add(PriceSnapshot(security_id=sec, last_price=D("6"), prev_close=D("6")))
        s.commit()

    pf = admin_client.get("/api/portfolio").json()
    p = next(x for x in pf if x["security_id"] == sec)
    # market_value_eur = 10 × 6 / 1.20 = 50
    assert abs(float(p["market_value_eur"]) - 50.0) < 0.01
    # invested_eur (coste) = 10×5/1.15 ≈ 43.48 → P/L latente ≈ 6.52
    assert abs(float(p["cost_eur"]) - (50.0 / 1.15)) < 0.01
    assert abs(float(p["unrealized_pnl_eur"]) - (50.0 - 50.0 / 1.15)) < 0.05


def test_exchange_rate_endpoint_por_divisa(admin_client, seed_markets, engine):
    """El endpoint de tipo de cambio devuelve el tipo de la divisa pedida (BCE)."""
    with Session(engine) as s:
        s.add(EcbRate(date="2024-01-09", currency="GBP", rate=D("0.86")))
        s.commit()
    r = admin_client.get("/api/markets/exchange-rate?date=2024-01-10&currency=GBP").json()
    assert r["source"] == "ecb"
    assert abs(float(r["rate"]) - 0.86) < 1e-9


def test_exchange_rate_eur_es_uno(admin_client, seed_markets):
    """EUR consigo misma → tipo 1, sin consultar Yahoo EUREUR=X."""
    r = admin_client.get("/api/markets/exchange-rate?date=2024-01-10&currency=EUR").json()
    assert r["source"] == "eur"
    assert float(r["rate"]) == 1.0


# ---------------------------------------------------------------------------
#  Regresión: import de backup rechaza divisa no-EUR con rate=1 (rompería carga)
# ---------------------------------------------------------------------------

def test_backup_import_rechaza_divisa_incoherente(admin_client, seed_markets):
    admin_client.patch("/api/admin/config/currencies", json={"currencies": ["USD", "GBP"]})
    admin_client.post("/api/securities", json={
        "name": "GBP Co", "yahoo_ticker": "GBPCO.L", "market": "ibex35", "currency": "GBP",
    })

    def _backup(rate):
        return {"version": "1", "positions": [{
            "security_ticker": "GBPCO.L", "transactions": [{
                "type": "buy", "date": "2024-01-10", "shares": "10", "price": "5",
                "fee": "0", "currency": "GBP", "exchange_rate": rate,
            }], "dividends": [],
        }]}

    # rate=1 con GBP → incoherente: NO se importa, queda en errores.
    bad = admin_client.post("/api/backup/import", json=_backup("1")).json()
    assert bad["transactions_added"] == 0
    assert any("incoherente" in e for e in bad["errors"])

    # rate válido → se importa.
    ok = admin_client.post("/api/backup/import", json=_backup("0.86")).json()
    assert ok["transactions_added"] == 1


# ---------------------------------------------------------------------------
#  Regresión: tras upgrade (solo USD), update_ecb_rates backfillea histórico
# ---------------------------------------------------------------------------

def test_valoracion_usd_sin_ecb_usa_tipo_de_transaccion(admin_client, seed_markets, engine):
    """
    Regresión (bug MSTR): un valor USD sin tipo BCE cacheado NO debe valorarse
    con tipo=1 (que trataría el dólar como euro e inflaría el valor). Debe caer
    al tipo de la transacción. 6 × 134.28 USD / 1.161 ≈ 694 € (no 805 €).
    """
    sec = admin_client.post("/api/securities", json={
        "name": "Strategy", "yahoo_ticker": "MSTR", "market": "nasdaq", "currency": "USD",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2026-06-03", "shares": "6", "price": "134.31",
        "fee": "3.47", "currency": "USD", "exchange_rate": "1.161",
    })
    # Snapshot en USD, SIN ninguna fila en ecb_rates.
    with Session(engine) as s:
        s.add(PriceSnapshot(security_id=sec, last_price=D("134.28"), prev_close=D("136.0")))
        s.commit()

    p = next(x for x in admin_client.get("/api/portfolio").json() if x["security_id"] == sec)
    # 6×134.28 / 1.161 ≈ 694 € (convertido), NO 805.68 (sin convertir).
    assert abs(float(p["market_value_eur"]) - (6 * 134.28 / 1.161)) < 1.0
    assert float(p["market_value_eur"]) < 750


def test_update_ecb_rates_backfill_si_solo_usd(db, monkeypatch):
    db.add(EcbRate(date=(date.today() - timedelta(days=3)).isoformat(), currency="USD", rate=D("1.1")))
    db.commit()
    captured = {}

    def fake_all(from_date, to_date):
        captured["from"] = from_date
        return {}
    monkeypatch.setattr(jobs._ecb, "fetch_all_rates", fake_all)

    jobs.update_ecb_rates(db)
    # Solo había USD → backfill completo (~5 años), no incremental desde hace 3 días.
    assert captured["from"] <= date.today() - timedelta(days=300)
