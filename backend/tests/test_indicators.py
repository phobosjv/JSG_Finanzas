"""
test_indicators.py
==================
Tests unitarios de services/indicators.py (compute_ranges).

Semantica de compute_ranges:
  - min_1y / max_1y : extremos de los ultimos 365 dias naturales desde ref.
  - min_2y / max_2y : extremos de los ultimos 730 dias desde ref.
  - min_5y / max_5y : extremos de los ultimos 1825 dias desde ref.

  Si hay algun precio dentro de la ventana → campo poblado.
  Si no hay ningun precio dentro de la ventana → None.
  Una serie de 180 dias tiene TODOS los precios dentro de cualquier ventana
  (1a, 2a, 5a), por lo que todos los campos salen poblados e iguales.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.services.indicators import RangeStats, compute_ranges


def D(x: str) -> Decimal:
    return Decimal(x)


REF = date(2024, 6, 1)   # fecha de referencia fija para todos los tests


def day(n: int) -> date:
    """REF - n dias."""
    return REF - timedelta(days=n)


# --------------------------------------------------------------------------
#  1. Serie vacia
# --------------------------------------------------------------------------

def test_serie_vacia():
    """Sin datos, todos los campos son None."""
    result = compute_ranges([])
    assert result == RangeStats(None, None, None, None, None, None)


# --------------------------------------------------------------------------
#  2. Un único punto
# --------------------------------------------------------------------------

def test_un_solo_punto():
    """Un solo precio: min_1y == max_1y == ese precio. min/max 2a y 5a iguales."""
    result = compute_ranges([(day(0), D("55.50"))], reference_date=REF)
    assert result.min_1y == D("55.50")
    assert result.max_1y == D("55.50")
    # El mismo precio cae en la ventana de 2a y 5a tambien
    assert result.min_2y == D("55.50")
    assert result.max_2y == D("55.50")
    assert result.min_5y == D("55.50")
    assert result.max_5y == D("55.50")


# --------------------------------------------------------------------------
#  3. Serie dentro del primer año
# --------------------------------------------------------------------------

def test_serie_corta_todos_dentro_del_primer_ano():
    """
    180 dias de datos (todos dentro de los 365 dias de ref).
    Precios del dia 179 al dia 0 (referencia): 100, 101, ..., 279.

    Los tres windows (1a, 2a, 5a) incluyen los mismos 180 precios porque
    todos estan dentro de 365 dias (y a fortiori dentro de 730 y 1825).
    """
    series = [(day(179 - i), D(str(100 + i))) for i in range(180)]
    result = compute_ranges(series, reference_date=REF)

    # Todos los precios dentro de los tres windows
    assert result.min_1y == D("100")
    assert result.max_1y == D("279")
    # 2a y 5a incluyen los mismos precios
    assert result.min_2y == D("100")
    assert result.max_2y == D("279")
    assert result.min_5y == D("100")
    assert result.max_5y == D("279")


# --------------------------------------------------------------------------
#  4. Serie que abarca justo 2 anos
# --------------------------------------------------------------------------

def test_serie_dos_anos():
    """
    730 dias de datos (precios 100..829, el mas antiguo a day(729)).
    cut_1y = REF - 365 → incluye solo los precios de day(364)..day(0)
      precios: 100+(729-364)=465 a 100+729=829
    cut_2y = REF - 730 → day(729) ya justo en el limite (>= cut_2y) → incluye todo
    min_1y > min_2y porque la ventana 1a excluye los precios mas bajos del inicio.
    """
    series = [(day(729 - i), D(str(100 + i))) for i in range(730)]
    result = compute_ranges(series, reference_date=REF)

    # Ventana 1a: solo los ultimos 365 dias
    # i minimo = 729 - 365 = 364 → precio = 100 + 364 = 464
    assert result.min_1y == D("464")
    assert result.max_1y == D("829")   # 100 + 729
    # Ventana 2a: incluye toda la serie
    assert result.min_2y == D("100")
    assert result.max_2y == D("829")
    # Ventana 5a: incluye toda la serie
    assert result.min_5y == D("100")
    assert result.max_5y == D("829")
    # El minimo de la ventana mas amplia es siempre menor o igual
    assert result.min_2y <= result.min_1y


# --------------------------------------------------------------------------
#  5. Serie que abarca 5+ anos
# --------------------------------------------------------------------------

def test_serie_cinco_anos():
    """
    1826 dias de datos (> 1825 = 5 anos).
    El primer punto es day(1825), justo en el borde del corte 5a.
    cut_5y = REF - 1825 → day(1825) esta exactamente en el borde (incluido).

    Precios: 100, 101, ..., 100+1825 = 1925.

    min_1y usa solo los ultimos 365 dias → precio mas bajo = 100+(1825-364) = 1561.
    min_2y usa los ultimos 730 dias      → precio mas bajo = 100+(1825-729) = 1196.
    min_5y usa los ultimos 1825 dias     → precio mas bajo = 100 (borde incluido).
    """
    series = [(day(1825 - i), D(str(100 + i))) for i in range(1826)]
    result = compute_ranges(series, reference_date=REF)

    # i minimo para 1a: 1825-365=1460 → precio=100+1460=1560
    # i minimo para 2a: 1825-730=1095 → precio=100+1095=1195
    assert result.min_1y == D("1560")
    assert result.max_1y == D("1925")   # 100 + 1825
    assert result.min_2y == D("1195")
    assert result.max_2y == D("1925")
    assert result.min_5y == D("100")    # precio del borde mas antiguo (incluido)
    assert result.max_5y == D("1925")

    # Orden invariante: mas amplio → minimo mas bajo o igual
    assert result.min_5y <= result.min_2y <= result.min_1y
    # El maximo es el mismo en todos los rangos (el precio mas alto es reciente)
    assert result.max_1y == result.max_2y == result.max_5y


# --------------------------------------------------------------------------
#  6. Precio fuera de la ventana de 5 anos → None
# --------------------------------------------------------------------------

def test_precio_fuera_de_5_anos_da_none_en_5a():
    """
    Unico precio a day(1826), un dia fuera del corte 5a (cut_5y = REF-1825).
    Ese precio NO entra en ninguna ventana → todos None.
    """
    result = compute_ranges([(day(1826), D("50"))], reference_date=REF)
    assert result.min_1y  is None
    assert result.max_1y  is None
    assert result.min_2y  is None
    assert result.max_2y  is None
    assert result.min_5y  is None
    assert result.max_5y  is None


# --------------------------------------------------------------------------
#  7. Datos solo en ventana 2a-5a (fuera del ultimo año)
# --------------------------------------------------------------------------

def test_datos_solo_en_ventana_2_a_5a():
    """
    Precios entre day(400) y day(366): fuera del 1er ano pero dentro del 2o.
    min_1y = None (nada en los ultimos 365 dias).
    min_2y y min_5y poblados.
    """
    series = [(day(400 - i), D(str(200 + i))) for i in range(35)]  # dias 400..366
    result = compute_ranges(series, reference_date=REF)

    assert result.min_1y is None    # nada en los ultimos 365 dias
    assert result.max_1y is None
    assert result.min_2y is not None   # hay datos entre 366-400 dias
    assert result.min_2y == D("200")   # precio del dia mas antiguo (day 400)
    # max_2y = precio mas alto de la serie (day 366 → 200+34=234)
    assert result.max_2y == D("234")
    assert result.min_5y == D("200")   # mismos datos
    assert result.max_5y == D("234")


# --------------------------------------------------------------------------
#  8. reference_date explicito en el pasado
# --------------------------------------------------------------------------

def test_reference_date_explicito():
    """
    Calcular rangos para una fecha pasada (ref=2020-01-01).
    Serie: 5 cierres en enero 2020.
    """
    ref = date(2020, 1, 5)
    series = [
        (date(2020, 1, 1), D("10")),
        (date(2020, 1, 2), D("12")),
        (date(2020, 1, 3), D("8")),
        (date(2020, 1, 4), D("15")),
        (date(2020, 1, 5), D("11")),
    ]
    result = compute_ranges(series, reference_date=ref)

    assert result.min_1y == D("8")
    assert result.max_1y == D("15")
    assert result.min_2y == D("8")
    assert result.max_2y == D("15")
    assert result.min_5y == D("8")
    assert result.max_5y == D("15")


# --------------------------------------------------------------------------
#  9. Desordenada: el resultado es identico al ordenado
# --------------------------------------------------------------------------

def test_serie_desordenada_produce_mismo_resultado():
    """El orden de entrada no afecta al resultado (se recorre por filtro de fecha)."""
    series_ord = [(day(i), D(str(100 + i))) for i in range(10)]
    series_rev = list(reversed(series_ord))

    r1 = compute_ranges(series_ord, reference_date=REF)
    r2 = compute_ranges(series_rev, reference_date=REF)

    assert r1 == r2
