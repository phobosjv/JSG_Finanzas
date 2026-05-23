"""
test_splits.py
==============
Tests de splits / contrasplits (v1.4.0).

Sección A: cálculo puro (calculations.py) — sin BD.
Sección B: endpoints admin CRUD de splits.
Sección C: integración split + portfolio (shares y coste ajustados).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.calculations import (
    Dividend,
    Split,
    Transaction,
    compute_position,
)


# ---------------------------------------------------------------------------
# Helpers de construcción
# ---------------------------------------------------------------------------

def _buy(d: str, shares: int | float, price: float, fee: float = 0) -> Transaction:
    return Transaction(
        type="buy",
        date=date.fromisoformat(d),
        shares=Decimal(str(shares)),
        price=Decimal(str(price)),
        fee=Decimal(str(fee)),
        exchange_rate=Decimal("1"),
    )


def _sell(d: str, shares: int | float, price: float, fee: float = 0) -> Transaction:
    return Transaction(
        type="sell",
        date=date.fromisoformat(d),
        shares=Decimal(str(shares)),
        price=Decimal(str(price)),
        fee=Decimal(str(fee)),
        exchange_rate=Decimal("1"),
    )


def _split(ex_date: str, num: int, den: int) -> Split:
    return Split(ex_date=date.fromisoformat(ex_date), ratio_num=num, ratio_den=den)


# ===========================================================================
# A — Cálculo puro
# ===========================================================================

class TestSplitCalculations:

    def test_sin_splits_comportamiento_intacto(self):
        """Con splits=[] el resultado debe ser idéntico al baseline sin splits."""
        txs = [_buy("2024-01-10", 100, 10)]
        r_sin = compute_position(txs, [])
        r_con = compute_position(txs, [], [])
        # 100 acc × 10 € = 1000 € invertidos
        assert r_sin.current_shares == r_con.current_shares
        assert r_sin.invested_eur == r_con.invested_eur

    def test_split_2_1_ajusta_acciones_y_precio(self):
        """
        Compra 100 acc × 10 €  →  split 2:1  →  200 acc × 5 €.
        Coste total = 1000 € (invariante).
        """
        txs = [_buy("2024-01-10", 100, 10)]
        splits = [_split("2024-06-01", 2, 1)]
        r = compute_position(txs, [], splits)
        # 100 × 2 = 200 acciones
        assert r.current_shares == Decimal("200")
        # precio medio = 1000 / 200 = 5 €
        assert r.avg_price_native == Decimal("5")
        # coste total invariante
        assert r.invested_eur == Decimal("1000")

    def test_contrasplit_1_2_ajusta_acciones_y_precio(self):
        """
        Compra 100 acc × 10 €  →  contrasplit 1:2  →  50 acc × 20 €.
        Coste total = 1000 € (invariante).
        """
        txs = [_buy("2024-01-10", 100, 10)]
        splits = [_split("2024-06-01", 1, 2)]
        r = compute_position(txs, [], splits)
        # 100 × (1/2) = 50 acciones
        assert r.current_shares == Decimal("50")
        assert r.avg_price_native == Decimal("20")
        assert r.invested_eur == Decimal("1000")

    def test_split_no_afecta_transacciones_posteriores(self):
        """
        El split solo normaliza transacciones ANTERIORES a ex_date.
        Una compra posterior no se modifica.
        """
        txs = [
            _buy("2024-01-10", 100, 10),   # antes del split → normalizada a 200 × 5
            _buy("2024-07-01", 50, 5),      # después del split → sin cambio
        ]
        splits = [_split("2024-06-01", 2, 1)]
        r = compute_position(txs, [], splits)
        # 200 + 50 = 250 acciones
        assert r.current_shares == Decimal("250")
        # coste total = 1000 + 50×5 = 1250 €
        assert r.invested_eur == Decimal("1250")

    def test_venta_post_split_ganancias_correctas(self):
        """
        Compra 100 acc × 10 €.
        Split 2:1 → 200 acc × 5 €.
        Venta 50 acc × 6 €.
        Ganancia = 50 × (6 - 5) = 50 €.
        Restante = 150 acc × 5 €, coste = 750 €.
        """
        txs = [
            _buy("2024-01-10", 100, 10),
            _sell("2024-08-01", 50, 6),
        ]
        splits = [_split("2024-06-01", 2, 1)]
        r = compute_position(txs, [], splits)
        # 200 - 50 = 150 acciones restantes
        assert r.current_shares == Decimal("150")
        # coste restante = 150 × 5 = 750 €
        assert r.invested_eur == Decimal("750")
        # ganancia realizada = 50 × (6 - 5) = 50 €
        assert r.realized_gain_eur == Decimal("50")

    def test_venta_pre_split_normalizada_correctamente(self):
        """
        Compra 100 acc × 10 €.
        Venta 30 acc × 12 € (antes del split) → ganancia = 60 €.
        Split 2:1.
        Posición: 140 acc × 5 €, coste = 700 €.

        Con normalización:
          compra normalizada: 200 acc × 5 €
          venta normalizada:   60 acc × 6 €
          ganancia = 60 × (6 - 5) = 60 € ✓
          restante = 200 - 60 = 140 acc ✓
        """
        txs = [
            _buy("2024-01-10", 100, 10),
            _sell("2024-03-01", 30, 12),
        ]
        splits = [_split("2024-06-01", 2, 1)]
        r = compute_position(txs, [], splits)
        assert r.current_shares == Decimal("140")
        assert r.invested_eur == Decimal("700")
        assert r.realized_gain_eur == Decimal("60")

    def test_dos_splits_consecutivos(self):
        """
        Compra 100 acc × 100 €.
        Split 1: 2:1 el 2024-06-01 → 200 acc × 50 €.
        Split 2: 3:2 el 2024-09-01 → 300 acc × 33.33 €.
        Coste total = 10 000 € (invariante, con tolerancia de precisión Decimal).
        """
        txs = [_buy("2024-01-10", 100, 100)]
        splits = [
            _split("2024-06-01", 2, 1),
            _split("2024-09-01", 3, 2),
        ]
        r = compute_position(txs, [], splits)
        # 100 × 2 × (3/2) = 300 acciones
        assert r.current_shares == Decimal("300")
        # coste = 10 000 € (invariante; puede haber error < 1 céntimo por división periódica)
        assert abs(r.invested_eur - Decimal("10000")) < Decimal("0.01")

    def test_compra_entre_dos_splits_solo_aplica_el_posterior(self):
        """
        Split 1: 2:1 el 2024-03-01
        Compra 100 acc × 5 € el 2024-05-01 (entre splits) → solo afectada por split2
        Split 2: 3:1 el 2024-09-01

        compra normalizada: 100 × 3 = 300 acc, precio = 5 / 3
        coste total = 300 × (5/3) = 500 € (invariante).
        """
        txs = [_buy("2024-05-01", 100, 5)]
        splits = [
            _split("2024-03-01", 2, 1),   # anterior a la compra → no afecta
            _split("2024-09-01", 3, 1),   # posterior → afecta
        ]
        r = compute_position(txs, [], splits)
        assert r.current_shares == Decimal("300")
        # coste = 100 × 5 = 500 € (invariante; puede haber error < 1 céntimo)
        assert abs(r.invested_eur - Decimal("500")) < Decimal("0.01")


# ===========================================================================
# B — Endpoints admin CRUD de splits
# ===========================================================================

def _crear_security_y_posicion(client, ticker="ITX.MC"):
    """
    Crea un valor y una posición con una compra usando 'client' (debe ser admin_client).
    Devuelve (sec_id, pos_id).
    """
    r = client.post("/api/securities", json={
        "name": "Test Corp",
        "yahoo_ticker": ticker,
        "market": "ibex35",
        "currency": "EUR",
    })
    assert r.status_code == 201, r.text
    sec_id = r.json()["id"]

    r2 = client.post("/api/portfolio/positions", json={"security_id": sec_id})
    assert r2.status_code == 201
    pos_id = r2.json()["id"]

    r3 = client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "buy", "date": "2024-01-10",
        "shares": "100", "price": "10.00",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    assert r3.status_code == 201
    return sec_id, pos_id


class TestSplitAdminEndpoints:

    def test_crear_split(self, admin_client, seed_markets):
        sec_id, _ = _crear_security_y_posicion(admin_client)
        resp = admin_client.post(f"/api/admin/securities/{sec_id}/splits", json={
            "ex_date": "2024-06-01",
            "ratio_num": 2,
            "ratio_den": 1,
            "notes": "Split 2 por 1",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["security_id"] == sec_id
        assert data["ex_date"] == "2024-06-01"
        assert data["ratio_num"] == 2
        assert data["ratio_den"] == 1
        assert data["notes"] == "Split 2 por 1"

    def test_listar_splits(self, admin_client, seed_markets):
        sec_id, _ = _crear_security_y_posicion(admin_client, "ACS.MC")
        # Crear dos splits
        admin_client.post(f"/api/admin/securities/{sec_id}/splits", json={
            "ex_date": "2024-03-01", "ratio_num": 2, "ratio_den": 1,
        })
        admin_client.post(f"/api/admin/securities/{sec_id}/splits", json={
            "ex_date": "2024-09-01", "ratio_num": 3, "ratio_den": 2,
        })
        resp = admin_client.get(f"/api/admin/securities/{sec_id}/splits")
        assert resp.status_code == 200
        splits = resp.json()
        assert len(splits) == 2
        # Ordenados por fecha
        assert splits[0]["ex_date"] == "2024-03-01"
        assert splits[1]["ex_date"] == "2024-09-01"

    def test_eliminar_split(self, admin_client, seed_markets):
        sec_id, _ = _crear_security_y_posicion(admin_client, "BKT.MC")
        r = admin_client.post(f"/api/admin/securities/{sec_id}/splits", json={
            "ex_date": "2024-06-01", "ratio_num": 2, "ratio_den": 1,
        })
        split_id = r.json()["id"]

        resp = admin_client.delete(f"/api/admin/splits/{split_id}")
        assert resp.status_code == 204

        # Ya no aparece en la lista
        lista = admin_client.get(f"/api/admin/securities/{sec_id}/splits").json()
        assert lista == []

    def test_crear_split_ratio_invalido(self, admin_client, seed_markets):
        sec_id, _ = _crear_security_y_posicion(admin_client, "ELE.MC")
        resp = admin_client.post(f"/api/admin/securities/{sec_id}/splits", json={
            "ex_date": "2024-06-01", "ratio_num": 0, "ratio_den": 1,
        })
        assert resp.status_code == 422

    def test_crear_split_security_no_existe(self, admin_client, seed_markets):
        resp = admin_client.post("/api/admin/securities/9999/splits", json={
            "ex_date": "2024-06-01", "ratio_num": 2, "ratio_den": 1,
        })
        assert resp.status_code == 404

    def test_eliminar_split_no_existe(self, admin_client, seed_markets):
        resp = admin_client.delete("/api/admin/splits/9999")
        assert resp.status_code == 404

    def test_crear_split_requiere_admin(self, auth_client, seed_markets):
        """Un usuario normal recibe 403 (la comprobación is_admin ocurre antes que la de security)."""
        resp = auth_client.post("/api/admin/securities/1/splits", json={
            "ex_date": "2024-06-01", "ratio_num": 2, "ratio_den": 1,
        })
        assert resp.status_code == 403


# ===========================================================================
# C — Integración split + portfolio
# ===========================================================================

class TestSplitPortfolioIntegration:

    def test_portfolio_refleja_shares_ajustadas_tras_split(
        self, admin_client, seed_markets
    ):
        """
        Tras un split 2:1, GET /portfolio debe mostrar el doble de acciones
        y el precio medio a la mitad, con el mismo coste total.
        Compra: 100 acc × 10 € → coste 1000 €.
        Split 2:1 → 200 acc × 5 €, coste 1000 €.
        """
        sec_id, pos_id = _crear_security_y_posicion(admin_client, "SAN.MC")

        # Registrar el split
        admin_client.post(f"/api/admin/securities/{sec_id}/splits", json={
            "ex_date": "2024-06-01",
            "ratio_num": 2,
            "ratio_den": 1,
        })

        resp = admin_client.get("/api/portfolio")
        assert resp.status_code == 200
        positions = resp.json()
        assert len(positions) == 1
        pos = positions[0]

        # 100 × 2 = 200 acciones
        assert Decimal(pos["shares"]) == Decimal("200")
        # coste total = 1000 € (invariante)
        assert Decimal(pos["cost_eur"]) == Decimal("1000")
        # precio medio = 1000 / 200 = 5 €
        assert Decimal(pos["avg_cost_eur"]) == Decimal("5")

    def test_venta_post_split_ganancias_correctas_via_api(
        self, admin_client, seed_markets
    ):
        """
        Compra 100 acc × 10 €.
        Split 2:1.
        Venta 50 acc × 6 €.
        Beneficio realizado = 50 × (6 - 5) = 50 €.
        """
        sec_id, pos_id = _crear_security_y_posicion(admin_client, "TEF.MC")
        admin_client.post(f"/api/admin/securities/{sec_id}/splits", json={
            "ex_date": "2024-06-01", "ratio_num": 2, "ratio_den": 1,
        })

        # Venta post-split: 50 acciones a 6 €
        r = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "sell", "date": "2024-08-01",
            "shares": "50", "price": "6.00",
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })
        assert r.status_code == 201

        resp = admin_client.get("/api/portfolio")
        assert resp.status_code == 200
        positions = [p for p in resp.json() if p["security_id"] == sec_id]
        assert len(positions) == 1
        pos = positions[0]

        # 200 - 50 = 150 acciones abiertas
        assert Decimal(pos["shares"]) == Decimal("150")
        # beneficio realizado = 50 € (mostrado en el resumen de cartera)
        assert Decimal(pos["realized_pnl_eur"]) == Decimal("50")
