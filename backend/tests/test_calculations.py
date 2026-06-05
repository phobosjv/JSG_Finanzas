"""
test_calculations.py
====================
Tests del nucleo financiero (services/calculations.py).

Filosofia de estos tests:
  * Cada caso lleva en comentario la aritmetica que justifica el resultado
    esperado. Si un test falla, el comentario permite saber si el fallo
    esta en el codigo o en la expectativa.
  * Los importes esperados se comparan con tolerancia minima: se opera con
    Decimal, asi que las cifras deben coincidir de forma practicamente exacta.
  * Casos elegidos para cubrir: precio medio ponderado, FIFO con venta
    parcial, venta total, dividendos, conversion de divisa (Nasdaq) y
    los errores de datos del usuario.

Ejecutar:  pytest test_calculations.py -v
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.calculations import (
    Transaction,
    Dividend,
    compute_position,
    value_position,
    daily_change,
    aggregate_portfolio,
    to_eur,
)


# --------------------------------------------------------------------------
#  Ayudas
# --------------------------------------------------------------------------

def D(x: str) -> Decimal:
    """Atajo para construir Decimal desde str (nunca desde float)."""
    return Decimal(x)


def approx_eq(a: Decimal, b: str, tol: str = "0.0001") -> bool:
    """Compara dos Decimal con una tolerancia minima."""
    return abs(a - Decimal(b)) <= Decimal(tol)


# Compra/venta en EUR: exchange_rate = 1
def buy_eur(d, shares, price, fee="0"):
    return Transaction("buy", d, D(shares), D(price), D(fee), D("1"))


def sell_eur(d, shares, price, fee="0"):
    return Transaction("sell", d, D(shares), D(price), D(fee), D("1"))


# --------------------------------------------------------------------------
#  1. Precio medio ponderado  (el ejemplo discutido en el diseno)
# --------------------------------------------------------------------------

def test_precio_medio_ponderado():
    """
    Compra 1: 10 acc a 100 EUR + 5 EUR comision = 1005 EUR -> 100.5 EUR/acc
    Compra 2: 20 acc a  90 EUR + 8 EUR comision = 1808 EUR ->  90.4 EUR/acc

    Total invertido = 1005 + 1808 = 2813 EUR
    Total acciones  = 30
    Precio medio    = 2813 / 30 = 93.766666... EUR/acc

    La media SIMPLE (100.5 + 90.4)/2 = 95.45 seria INCORRECTA: ignora que
    se compraron mas acciones a precio bajo.
    """
    txs = [
        buy_eur(date(2023, 1, 10), "10", "100", "5"),
        buy_eur(date(2023, 3, 15), "20", "90", "8"),
    ]
    r = compute_position(txs, [])

    assert r.current_shares == D("30")
    assert approx_eq(r.invested_native, "2813")
    assert approx_eq(r.invested_eur, "2813")
    assert approx_eq(r.avg_price_native, "93.766667", tol="0.00001")
    assert r.realized_gain_native == D("0")  # nada vendido aun
    assert not r.is_closed


# --------------------------------------------------------------------------
#  2. Venta parcial con FIFO
# --------------------------------------------------------------------------

def test_venta_parcial_fifo():
    """
    Compra 1: 10 acc a 100 EUR, sin comision -> lote A, 100 EUR/acc
    Compra 2: 10 acc a 200 EUR, sin comision -> lote B, 200 EUR/acc
    Venta:    15 acc a 300 EUR, sin comision

    FIFO: la venta consume primero el lote A entero (10 acc) y luego
    5 acc del lote B.

    Ingreso venta = 15 * 300 = 4500 EUR
      - tramo lote A: 10/15 de 4500 = 3000 ; coste 10*100 = 1000 ; +2000
      - tramo lote B:  5/15 de 4500 = 1500 ; coste  5*200 = 1000 ;  +500
    Ganancia realizada total = 2500 EUR

    Quedan vivas: 5 acc del lote B -> invertido 5*200 = 1000 EUR
    """
    txs = [
        buy_eur(date(2023, 1, 1), "10", "100"),
        buy_eur(date(2023, 2, 1), "10", "200"),
        sell_eur(date(2023, 6, 1), "15", "300"),
    ]
    r = compute_position(txs, [])

    assert r.current_shares == D("5")
    assert approx_eq(r.invested_native, "1000")
    assert approx_eq(r.realized_gain_native, "2500")
    assert not r.is_closed

    # Dos emparejamientos venta-compra para Hacienda
    assert len(r.sale_matches) == 2
    m_a, m_b = r.sale_matches
    assert m_a.buy_date == date(2023, 1, 1)
    assert m_a.shares == D("10")
    assert approx_eq(m_a.gain_native, "2000")
    assert m_b.buy_date == date(2023, 2, 1)
    assert m_b.shares == D("5")
    assert approx_eq(m_b.gain_native, "500")


# --------------------------------------------------------------------------
#  3. Venta total: la posicion queda cerrada
# --------------------------------------------------------------------------

def test_venta_total_posicion_cerrada():
    """
    Compra: 50 acc a 20 EUR + 10 comision = 1010 EUR
    Venta:  50 acc a 25 EUR -  10 comision = 1240 EUR neto

    Ganancia realizada = 1240 - 1010 = 230 EUR
    Acciones vivas = 0 -> is_closed = True
    """
    txs = [
        buy_eur(date(2022, 5, 1), "50", "20", "10"),
        sell_eur(date(2024, 5, 1), "50", "25", "10"),
    ]
    r = compute_position(txs, [])

    assert r.current_shares == D("0")
    assert r.is_closed
    assert approx_eq(r.invested_native, "0")  # no queda nada vivo
    assert approx_eq(r.realized_gain_native, "230")


# --------------------------------------------------------------------------
#  3b. Umbral de "polvo": posiciones residuales por redondeo (DUST_THRESHOLD)
# --------------------------------------------------------------------------

def test_posicion_residual_polvo_se_considera_cerrada():
    """
    Compra 10 acc a 6 €, vende 9,999 acc: queda un residuo de 0,001 acc.
    Coste vivo = 0,001 × 6 = 0,006 € < DUST_THRESHOLD (0,10) → cerrada.
    (Reproduce el caso del usuario: 0 € y ~0 participaciones, pero is_closed
    daba False por el residuo de redondeo.)
    """
    txs = [
        buy_eur(date(2022, 1, 1), "10", "6"),
        sell_eur(date(2023, 1, 1), "9.999", "8"),
    ]
    r = compute_position(txs, [])

    assert r.current_shares == D("0.001")        # queda el polvo
    assert r.invested_native < D("0.10")          # coste vivo ínfimo
    assert r.is_closed                            # pero se considera cerrada


def test_posicion_pequena_pero_real_sigue_abierta():
    """
    Una posición con coste vivo POR ENCIMA del umbral sigue abierta:
    compra 1 acc a 6 € (coste 6 € > 0,10) → abierta.
    """
    txs = [buy_eur(date(2022, 1, 1), "1", "6")]
    r = compute_position(txs, [])

    assert r.current_shares == D("1")
    assert not r.is_closed


def test_umbral_polvo_justo_por_debajo_y_por_encima():
    """
    Frontera del umbral: coste vivo 0,09 € → cerrada; 0,11 € → abierta.
    Se usa precio 1 € para que coste vivo = participaciones.
    """
    # 0,09 acc a 1 € → coste vivo 0,09 < 0,10 → cerrada
    r_bajo = compute_position([buy_eur(date(2022, 1, 1), "0.09", "1")], [])
    assert r_bajo.is_closed

    # 0,11 acc a 1 € → coste vivo 0,11 > 0,10 → abierta
    r_alto = compute_position([buy_eur(date(2022, 1, 1), "0.11", "1")], [])
    assert not r_alto.is_closed


# --------------------------------------------------------------------------
#  4. Dividendos intercalados
# --------------------------------------------------------------------------

def test_dividendos_netos():
    """
    El dividendo se cobra sobre las acciones que se tenian EN SU FECHA,
    dato que viaja en 'shares_at_date' y NO se recalcula desde la posicion.

    Dividendo 1: bruto 100 EUR, retencion 19 EUR -> neto 81 EUR
    Dividendo 2: bruto  50 EUR, retencion  9.5 EUR -> neto 40.5 EUR
    Neto total = 121.5 EUR
    """
    txs = [buy_eur(date(2023, 1, 1), "100", "10")]
    divs = [
        Dividend(date(2023, 6, 1), D("100"), D("100"), D("19"), D("1")),
        Dividend(date(2023, 12, 1), D("100"), D("50"), D("9.5"), D("1")),
    ]
    r = compute_position(txs, divs)

    assert approx_eq(r.dividends_net_native, "121.5")
    assert approx_eq(r.dividends_net_eur, "121.5")


# --------------------------------------------------------------------------
#  5. Conversion de divisa: un valor del Nasdaq
# --------------------------------------------------------------------------

def test_nasdaq_conversion_divisa():
    """
    El BCE publica EUR/USD como 'USD por 1 EUR'. euros = dolares / rate.

    Compra: 10 acc a 150 USD + 5 USD comision = 1505 USD
            cambio del dia 1.10  ->  1505 / 1.10 = 1368.181818... EUR
    Venta:  10 acc a 200 USD - 5 USD comision = 1995 USD
            cambio del dia 1.25  ->  1995 / 1.25 = 1596.00 EUR

    Ganancia realizada en USD = 1995 - 1505 = 490 USD
    Ganancia realizada en EUR = 1596.00 - 1368.1818... = 227.8181... EUR

    Observacion: el resultado en EUR NO es 490/algo. Mezcla el movimiento
    de la accion y el del tipo de cambio. Es correcto y esperado.
    """
    txs = [
        Transaction("buy", date(2023, 1, 1), D("10"), D("150"), D("5"), D("1.10")),
        Transaction("sell", date(2024, 1, 1), D("10"), D("200"), D("5"), D("1.25")),
    ]
    r = compute_position(txs, [])

    assert r.current_shares == D("0")
    assert approx_eq(r.realized_gain_native, "490")
    assert approx_eq(r.realized_gain_eur, "227.818182", tol="0.0001")


def test_to_eur_basico():
    """euros = dolares / rate ; con rate=1 el importe pasa intacto."""
    assert approx_eq(to_eur(D("110"), D("1.10")), "100")
    assert approx_eq(to_eur(D("250"), D("1")), "250")
    with pytest.raises(ValueError):
        to_eur(D("100"), D("0"))


# --------------------------------------------------------------------------
#  6. Valoracion a precio de mercado de hoy
# --------------------------------------------------------------------------

def test_valoracion_beneficio_latente():
    """
    Compra: 10 acc a 100 EUR (sin comision) -> invertido 1000 EUR, vivas 10
    Cotizacion hoy: 130 EUR, valor en EUR (rate=1)

    Valor de mercado = 10 * 130 = 1300 EUR
    Beneficio latente = 1300 - 1000 = 300 EUR
    % latente = 300 / 1000 * 100 = 30%
    Total = realizado(0) + latente(300) + dividendos(0) = 300 EUR
    """
    txs = [buy_eur(date(2023, 1, 1), "10", "100")]
    r = compute_position(txs, [])
    v = value_position(r, current_price_native=D("130"), current_rate=D("1"))

    assert approx_eq(v["market_value_eur"], "1300")
    assert approx_eq(v["unrealized_gain_eur"], "300")
    assert approx_eq(v["unrealized_gain_pct"], "30")
    assert approx_eq(v["total_gain_eur"], "300")


def test_variacion_diaria():
    """
    10 acciones. Cierre anterior 50 EUR, precio hoy 52 EUR.
    Variacion por accion = 2 EUR
    Variacion de la posicion = 10 * 2 = 20 EUR
    Variacion % = 2 / 50 * 100 = 4%
    """
    c = daily_change(
        shares=D("10"), last_price=D("52"),
        prev_close=D("50"), current_rate=D("1"),
    )
    assert approx_eq(c["daily_change_native"], "20")
    assert approx_eq(c["daily_change_pct"], "4")


# --------------------------------------------------------------------------
#  7. Agregado de cartera
# --------------------------------------------------------------------------

def test_agregado_cartera():
    """
    Dos posiciones ya valoradas en EUR:
      Pos 1: invertido 1000, valor 1300, realizado 0,   latente 300, div 50
      Pos 2: invertido 2000, valor 1800, realizado 100, latente -200, div 0

    Invertido total = 3000 ; Valor total = 3100 ; Diferencia = 100
    Total = realizado(100) + latente(100) + dividendos(50) = 250
    % agregado = latente(100) / invertido(3000) * 100 = 3.333...%
    """
    posiciones = [
        {
            "invested_eur": D("1000"), "market_value_eur": D("1300"),
            "realized_gain_eur": D("0"), "unrealized_gain_eur": D("300"),
            "dividends_net_eur": D("50"),
        },
        {
            "invested_eur": D("2000"), "market_value_eur": D("1800"),
            "realized_gain_eur": D("100"), "unrealized_gain_eur": D("-200"),
            "dividends_net_eur": D("0"),
        },
    ]
    a = aggregate_portfolio(posiciones)

    assert approx_eq(a["invested_eur"], "3000")
    assert approx_eq(a["market_value_eur"], "3100")
    assert approx_eq(a["difference_eur"], "100")
    assert approx_eq(a["total_gain_eur"], "250")
    # El % refleja el beneficio TOTAL (latente + realizado + dividendos) / invertido.
    # total_gain = realizado(100) + latente(100) + dividendos(50) = 250
    # avg_return_pct = 250/3000*100 = 8.333...%
    assert approx_eq(a["avg_return_pct"], "8.333333", tol="0.0001")


# --------------------------------------------------------------------------
#  8. Casos limite y errores de datos
# --------------------------------------------------------------------------

def test_vender_de_mas_lanza_error():
    """
    Vender mas acciones de las compradas es un error de datos del usuario.
    El modulo debe DETENERSE, no devolver numeros incorrectos en silencio.
    """
    txs = [
        buy_eur(date(2023, 1, 1), "10", "100"),
        sell_eur(date(2023, 6, 1), "15", "120"),  # solo hay 10
    ]
    with pytest.raises(ValueError, match="acciones"):
        compute_position(txs, [])


def test_posicion_vacia():
    """Sin transacciones: todo a cero, posicion cerrada."""
    r = compute_position([], [])
    assert r.current_shares == D("0")
    assert r.is_closed
    assert r.realized_gain_native == D("0")
    assert r.dividends_net_native == D("0")


def test_orden_cronologico_forzado():
    """
    Las transacciones se pasan DESORDENADAS a proposito.
    El modulo debe ordenarlas: si procesara la venta antes que la compra
    fallaria. Compra 10 a 100, venta 10 a 150 -> ganancia 500.
    """
    txs = [
        sell_eur(date(2023, 6, 1), "10", "150"),  # fecha posterior, va 2o
        buy_eur(date(2023, 1, 1), "10", "100"),   # fecha anterior, va 1o
    ]
    r = compute_position(txs, [])
    assert r.is_closed
    assert approx_eq(r.realized_gain_native, "500")


def test_compra_y_venta_mismo_dia():
    """
    Misma fecha para compra y venta: la compra debe procesarse primero
    (no se puede vender de una cola vacia). Compra 5 a 10, venta 5 a 12.
    Ganancia = 5*12 - 5*10 = 10.
    """
    txs = [
        sell_eur(date(2023, 3, 1), "5", "12"),
        buy_eur(date(2023, 3, 1), "5", "10"),
    ]
    r = compute_position(txs, [])
    assert r.is_closed
    assert approx_eq(r.realized_gain_native, "10")
