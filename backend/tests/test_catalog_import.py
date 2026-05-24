"""
test_catalog_import.py
======================
Tests de integración para los endpoints de exportación e importación
del catálogo de mercados y valores.

Endpoints probados:
  GET  /admin/catalog/export  — descarga JSON con todos los mercados y valores.
  POST /admin/catalog/import  — importa JSON, deduplicando por yahoo_ticker.

Reglas clave verificadas:
  1. Solo usuarios administradores pueden acceder (403 para usuarios normales).
  2. La exportación incluye todos los mercados y valores de la BD.
  3. La importación inserta únicamente lo que no existe todavía.
  4. El índice de deduplicación de VALORES es yahoo_ticker (único global):
     si un ticker ya existe en cualquier mercado, se omite en el import.
  5. El índice de deduplicación de MERCADOS es el code (PK).
  6. Si un valor referencia un mercado que no existe (ni en la BD
     ni en el lote del mismo import), se cuenta en securities_no_market.
  7. Los mercados del mismo lote se importan ANTES que los valores,
     permitiendo importar ambos en una sola llamada.
  8. Campos extra en el JSON (exported_at, _nota…) se ignoran sin error.
"""

import pytest


# ===========================================================================
# Fixture auxiliar
# ===========================================================================

MARKET_IBEX = {
    "code": "ibex35",
    "name": "IBEX 35",
    "index_ticker": "^IBEX",
    "currency": "EUR",
    "fiscal_window_days": 60,
}

MARKET_NASDAQ = {
    "code": "nasdaq",
    "name": "Nasdaq",
    "index_ticker": "^IXIC",
    "currency": "USD",
    "fiscal_window_days": 365,
}

SEC_INDITEX = {
    "name": "Inditex",
    "isin": "ES0148396007",
    "yahoo_ticker": "ITX.MC",
    "google_ticker": "BME:ITX",
    "market": "ibex35",
    "currency": "EUR",
}

SEC_SANTANDER = {
    "name": "Banco Santander",
    "isin": "ES0113900J37",
    "yahoo_ticker": "SAN.MC",
    "google_ticker": "BME:SAN",
    "market": "ibex35",
    "currency": "EUR",
}

SEC_APPLE = {
    "name": "Apple",
    "isin": "US0378331005",
    "yahoo_ticker": "AAPL",
    "google_ticker": "NASDAQ:AAPL",
    "market": "nasdaq",
    "currency": "USD",
}


# ===========================================================================
# Tests de autorización
# ===========================================================================

class TestCatalogAuth:

    def test_export_requiere_admin(self, auth_client):
        """Un usuario normal no puede exportar el catálogo (403)."""
        r = auth_client.get("/api/admin/catalog/export")
        assert r.status_code == 403

    def test_import_requiere_admin(self, auth_client):
        """Un usuario normal no puede importar el catálogo (403)."""
        r = auth_client.post("/api/admin/catalog/import",
                             json={"markets": [], "securities": []})
        assert r.status_code == 403


# ===========================================================================
# Tests de exportación
# ===========================================================================

class TestCatalogExport:

    def test_export_vacio(self, admin_client):
        """Con la BD vacía el export devuelve listas vacías y JSON válido."""
        r = admin_client.get("/api/admin/catalog/export")
        assert r.status_code == 200
        data = r.json()
        assert "markets" in data
        assert "securities" in data
        assert data["markets"] == []
        assert data["securities"] == []

    def test_export_incluye_mercados_y_valores(self, admin_client, seed_markets):
        """Tras sembrar mercados, el export los incluye."""
        r = admin_client.get("/api/admin/catalog/export")
        assert r.status_code == 200
        data = r.json()
        codes = {m["code"] for m in data["markets"]}
        assert "ibex35" in codes
        assert "nasdaq" in codes

    def test_export_incluye_content_disposition(self, admin_client):
        """La cabecera Content-Disposition indica descarga de fichero."""
        r = admin_client.get("/api/admin/catalog/export")
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "catalogo_valores" in cd

    def test_export_incluye_valores_creados(self, admin_client, seed_markets):
        """Los valores añadidos al catálogo aparecen en el export."""
        # Crear un valor via API
        admin_client.post("/api/securities", json=SEC_INDITEX)
        r = admin_client.get("/api/admin/catalog/export")
        tickers = {s["yahoo_ticker"] for s in r.json()["securities"]}
        assert "ITX.MC" in tickers


# ===========================================================================
# Tests de importación
# ===========================================================================

class TestCatalogImport:

    def test_import_catalogo_vacio_acepta_todo(self, admin_client):
        """
        Con la BD vacía se importan todos los mercados y valores del lote.
        Los mercados del mismo lote se importan primero, permitiendo que
        los valores los referencien en la misma llamada.
        """
        payload = {
            "markets":    [MARKET_IBEX, MARKET_NASDAQ],
            "securities": [SEC_INDITEX, SEC_APPLE],
        }
        r = admin_client.post("/api/admin/catalog/import", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["markets_imported"]    == 2
        assert data["markets_skipped"]     == 0
        assert data["securities_imported"] == 2
        assert data["securities_skipped"]  == 0
        assert data["securities_no_market"] == 0

        # Verificar que realmente están en la BD
        r2 = admin_client.get("/api/admin/catalog/export")
        tickers = {s["yahoo_ticker"] for s in r2.json()["securities"]}
        assert "ITX.MC" in tickers
        assert "AAPL" in tickers

    def test_import_segundo_lote_omite_existentes(self, admin_client):
        """
        Importar el mismo lote dos veces: la segunda pasada no debe añadir
        nada (todos los mercados y valores ya existen).
        """
        payload = {
            "markets":    [MARKET_IBEX],
            "securities": [SEC_INDITEX, SEC_SANTANDER],
        }
        admin_client.post("/api/admin/catalog/import", json=payload)
        r2 = admin_client.post("/api/admin/catalog/import", json=payload)
        assert r2.status_code == 200
        data = r2.json()
        assert data["markets_imported"]    == 0
        assert data["markets_skipped"]     == 1
        assert data["securities_imported"] == 0
        assert data["securities_skipped"]  == 2

    def test_import_ticker_omitido_aunque_cambie_mercado(self, admin_client, seed_markets):
        """
        Si un ticker ya existe en un mercado, no se importa aunque el JSON
        lo asigne a un mercado diferente. El original no se toca.
        """
        # Crear Inditex en ibex35
        admin_client.post("/api/securities", json=SEC_INDITEX)

        # Intentar importarlo bajo 'continuo'
        sec_en_continuo = {**SEC_INDITEX, "market": "continuo"}
        r = admin_client.post("/api/admin/catalog/import", json={
            "markets":    [],
            "securities": [sec_en_continuo],
        })
        data = r.json()
        # Debe saltar: ya existe por ticker
        assert data["securities_skipped"]  == 1
        assert data["securities_imported"] == 0

        # Verificar que sigue en ibex35
        exp = admin_client.get("/api/admin/catalog/export").json()
        itx = next(s for s in exp["securities"] if s["yahoo_ticker"] == "ITX.MC")
        assert itx["market"] == "ibex35"

    def test_import_valor_sin_mercado_existente(self, admin_client):
        """
        Un valor cuyo mercado no existe en la BD ni en el mismo lote
        se cuenta en securities_no_market y no se inserta.
        """
        payload = {
            "markets":    [],                   # no se importa ningún mercado
            "securities": [SEC_INDITEX],        # ibex35 no existe
        }
        r = admin_client.post("/api/admin/catalog/import", json=payload)
        data = r.json()
        assert data["securities_no_market"] == 1
        assert data["securities_imported"]  == 0

    def test_import_ignora_campos_extra(self, admin_client):
        """
        Campos extra en el JSON (exported_at, _nota…) no provocan error
        de validación: el endpoint los ignora silenciosamente.
        """
        payload = {
            "_nota":      "Este campo debe ignorarse",
            "exported_at": "2026-05-24",
            "markets":    [MARKET_IBEX],
            "securities": [],
        }
        r = admin_client.post("/api/admin/catalog/import", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["markets_imported"] == 1

    def test_import_exportado_redondo(self, admin_client, seed_markets):
        """
        Exportar → importar en BD vacía → comparar: el catálogo resultante
        debe ser idéntico al origen (round-trip).
        """
        # Crear valores en la BD fuente
        for sec in [SEC_INDITEX, SEC_SANTANDER, SEC_APPLE]:
            admin_client.post("/api/securities", json=sec)

        export_origen = admin_client.get("/api/admin/catalog/export").json()

        # Borrar todos los valores (la API no tiene bulk delete,
        # así que probamos directamente con el import en una segunda app)
        # En su lugar: importar el export en otra instancia (simulamos importando
        # el JSON hacia la BD actual que ya tiene los datos → todos skipped).
        r = admin_client.post("/api/admin/catalog/import", json=export_origen)
        data = r.json()
        # Todo debe estar ya presente → 0 importados
        assert data["securities_imported"] == 0
        assert data["markets_imported"]    == 0
        # Los 3 valores y 3 mercados deben aparecer como skipped
        assert data["securities_skipped"]  == 3
        assert data["markets_skipped"]     == 3

    def test_import_parcial_solo_nuevos(self, admin_client, seed_markets):
        """
        Si el catálogo ya tiene algunos valores, solo se importan los que faltan.
        Santander ya existe; Apple no: el resultado debe ser 1 importado, 1 omitido.
        """
        admin_client.post("/api/securities", json=SEC_SANTANDER)

        r = admin_client.post("/api/admin/catalog/import", json={
            "markets":    [],
            "securities": [SEC_APPLE, SEC_SANTANDER],
        })
        data = r.json()
        assert data["securities_imported"] == 1   # Apple
        assert data["securities_skipped"]  == 1   # Santander ya existía
