"""
test_import_export_v178.py
==========================
Tests del import/export ampliado (v1.7.8):
  * Export CSV de operaciones (round-trip con import-csv).
  * recurring_plans en el backup de usuario (export + import).
  * Mercados (con market_type) en el backup admin (export + import).
"""

import csv as _csv
import io


def _sec(admin_client, ticker, market="ibex35"):
    return admin_client.post("/api/securities", json={
        "name": ticker, "yahoo_ticker": ticker, "market": market, "currency": "EUR",
    }).json()["id"]


def _fund_markets(admin_client):
    admin_client.post("/api/admin/markets", json={
        "code": "fondos_a", "name": "Fondos A", "currency": "EUR",
        "fiscal_window_days": 365, "market_type": "fund",
    })


# ---------------------------------------------------------------------------
#  Export CSV
# ---------------------------------------------------------------------------

def test_export_csv_round_trip(admin_client, seed_markets):
    sec = _sec(admin_client, "SAN.MC")
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2023-01-15", "shares": "100", "price": "3.25",
        "fee": "0.5", "currency": "EUR", "exchange_rate": "1",
    })
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "sell", "date": "2024-06-10", "shares": "40", "price": "4.10",
        "fee": "0.5", "currency": "EUR", "exchange_rate": "1",
    })
    admin_client.post(f"/api/portfolio/{pos}/dividends", json={
        "date": "2023-12-01", "shares_at_date": "100", "gross_per_share": "0.2",
        "gross_amount": "20", "withholding_tax": "3.8", "currency": "EUR", "exchange_rate": "1",
    })

    resp = admin_client.get("/api/portfolio/export-csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]

    rows = list(_csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 3
    types = sorted(r["type"] for r in rows)
    assert types == ["buy", "dividend", "sell"]
    div_row = next(r for r in rows if r["type"] == "dividend")
    assert div_row["gross_per_share"] == "0.2"
    assert div_row["price"] == ""   # dividendos sin price

    # Round-trip: reimportar el CSV exportado no duplica (todo ya existe).
    import_rows = []
    for r in rows:
        import_rows.append({
            "type": r["type"], "ticker": r["ticker"], "date": r["date"],
            "shares": r["shares"],
            "price": r["price"] or None,
            "gross_per_share": r["gross_per_share"] or None,
            "gross_amount": r["gross_amount"] or None,
            "fee": r["fee"] or 0,
            "withholding_tax": r["withholding_tax"] or 0,
            "currency": r["currency"], "exchange_rate": r["exchange_rate"],
        })
    res = admin_client.post("/api/portfolio/import-csv", json={"rows": import_rows}).json()
    assert res["transactions_added"] == 0
    assert res["dividends_added"] == 0
    assert res["skipped"] == 3


# ---------------------------------------------------------------------------
#  recurring_plans en backup de usuario
# ---------------------------------------------------------------------------

def test_backup_usuario_incluye_y_restaura_planes(admin_client):
    _fund_markets(admin_client)
    sec = _sec(admin_client, "0PFUND.F", market="fondos_a")
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    # Plan futuro (no crea compras): start/end futuros.
    admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "200", "frequency": "monthly",
        "start_date": "2099-01-01", "end_date": "2099-06-01",
    })

    backup = admin_client.get("/api/backup/export").json()
    pos_entry = next(p for p in backup["positions"] if p["security_ticker"] == "0PFUND.F")
    assert len(pos_entry["recurring_plans"]) == 1
    assert pos_entry["recurring_plans"][0]["frequency"] == "monthly"

    # Cancelar el plan y restaurarlo desde el backup.
    plan_id = admin_client.get("/api/portfolio/recurring-plans").json()[0]["id"]
    admin_client.delete(f"/api/portfolio/recurring-plans/{plan_id}")
    assert admin_client.get("/api/portfolio/recurring-plans").json() == []

    admin_client.post("/api/backup/import", json=backup)
    plans = admin_client.get("/api/portfolio/recurring-plans").json()
    assert len(plans) == 1
    assert float(plans[0]["amount_per_period"]) == 200.0


# ---------------------------------------------------------------------------
#  Mercados (market_type) en backup admin
# ---------------------------------------------------------------------------

def test_backup_admin_exporta_mercados_con_tipo(admin_client):
    admin_client.post("/api/admin/markets", json={
        "code": "etfs_x", "name": "ETFs X", "currency": "EUR",
        "fiscal_window_days": 60, "market_type": "etf",
    })
    data = admin_client.get("/api/admin/backup/export").json()
    by_code = {m["code"]: m for m in data["markets"]}
    assert by_code["etfs_x"]["market_type"] == "etf"


def test_backup_admin_importa_mercados(admin_client):
    payload = {
        "version": "admin_1",
        "markets": [
            {"code": "nuevo_crypto", "name": "Nuevo Crypto", "currency": "EUR",
             "fiscal_window_days": 60, "market_type": "crypto"},
        ],
        "users": [],
        "securities": [],
        "portfolios": [],
    }
    r = admin_client.post("/api/admin/backup/import", json=payload)
    assert r.status_code == 200, r.text
    mkts = {m["code"]: m for m in admin_client.get("/api/markets/list").json()}
    assert "nuevo_crypto" in mkts
    assert mkts["nuevo_crypto"]["market_type"] == "crypto"
