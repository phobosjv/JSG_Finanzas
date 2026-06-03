"""
test_v179.py
============
Tests de v1.7.9:
  * Export a Ghostfolio (round-trip con import-ghostfolio).
  * update_snapshots(batch=True): usa fetch_live_quotes (un lote) — se mockea el
    proveedor para no llamar a Yahoo.
"""

from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import PriceHistory, PriceSnapshot
from app.providers.base import LiveQuote
from app.scheduler import jobs


def _sec(admin_client, ticker, market="ibex35"):
    return admin_client.post("/api/securities", json={
        "name": ticker, "yahoo_ticker": ticker, "market": market, "currency": "EUR",
    }).json()["id"]


# ---------------------------------------------------------------------------
#  Export Ghostfolio
# ---------------------------------------------------------------------------

def test_export_ghostfolio_round_trip(admin_client, seed_markets):
    sec = _sec(admin_client, "SAN.MC")
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2023-01-15", "shares": "100", "price": "3.25",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    admin_client.post(f"/api/portfolio/{pos}/dividends", json={
        "date": "2023-12-01", "shares_at_date": "100", "gross_per_share": "0.2",
        "gross_amount": "20", "withholding_tax": "0", "currency": "EUR", "exchange_rate": "1",
    })

    data = admin_client.get("/api/portfolio/export-ghostfolio").json()
    assert "activities" in data
    acts = data["activities"]
    assert len(acts) == 2
    types = sorted(a["type"] for a in acts)
    assert types == ["BUY", "DIVIDEND"]
    buy = next(a for a in acts if a["type"] == "BUY")
    assert buy["symbol"] == "SAN.MC"
    assert buy["quantity"] == 100.0
    assert buy["unitPrice"] == 3.25

    # Round-trip: reimportar no duplica (todo ya existe).
    res = admin_client.post("/api/portfolio/import-ghostfolio", json=data).json()
    assert res["transactions_added"] == 0
    assert res["dividends_added"] == 0
    assert res["skipped"] == 2


# ---------------------------------------------------------------------------
#  update_snapshots batch (sin red: se mockea el proveedor)
# ---------------------------------------------------------------------------

def test_update_snapshots_batch_mockeado(admin_client, seed_markets, engine, monkeypatch):
    sec = _sec(admin_client, "BATCH.MC")
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec, date="2024-01-10", close=D("10")))
        s.add(PriceHistory(security_id=sec, date="2024-01-11", close=D("11")))
        s.commit()

    # Mock del proveedor: devuelve un lote con la cotización del ticker pedido.
    def fake_batch(tickers):
        return {
            tk: LiveQuote(
                last_price=D("12.50"), prev_close=D("12.00"),
                daily_change_pct=D("4.17"), last_dividend=None,
                quote_time="2024-01-12T00:00:00+00:00",
            )
            for tk in tickers
        }
    monkeypatch.setattr(jobs._yahoo, "fetch_live_quotes", fake_batch)

    with Session(engine) as s:
        jobs.update_snapshots(s, only_ids={sec}, with_dividends=False, batch=True)
        snap = s.get(PriceSnapshot, sec)
        assert snap is not None
        assert float(snap.last_price) == 12.50
        assert float(snap.prev_close) == 12.00
