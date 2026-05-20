"""
test_backup_service.py
======================
Tests unitarios de services/backup.py.

Las funciones son puras (sin I/O), así que no necesitan BD ni fixtures.
"""

from app.services.backup import BACKUP_VERSION, ImportResult, build_export, validate_backup


# ---------------------------------------------------------------------------
#  build_export
# ---------------------------------------------------------------------------

def test_build_export_incluye_version():
    result = build_export([])
    assert result["version"] == BACKUP_VERSION


def test_build_export_incluye_positions():
    positions = [{"security_ticker": "SAN.MC"}, {"security_ticker": "AAPL"}]
    result = build_export(positions)
    assert result["positions"] is positions


def test_build_export_exported_at_formato_iso():
    # formato esperado: YYYY-MM-DDTHH:MM:SS (sin zona horaria ni microsegundos)
    ts = build_export([])["exported_at"]
    assert len(ts) == 19
    assert ts[4] == "-" and ts[7] == "-" and ts[10] == "T"


# ---------------------------------------------------------------------------
#  validate_backup
# ---------------------------------------------------------------------------

def test_validate_backup_correcto():
    data = {"version": BACKUP_VERSION, "positions": []}
    assert validate_backup(data) == []


def test_validate_backup_version_incorrecta():
    data = {"version": "99", "positions": []}
    errors = validate_backup(data)
    assert any("Versión" in e for e in errors)


def test_validate_backup_falta_positions():
    data = {"version": BACKUP_VERSION}
    errors = validate_backup(data)
    assert any("positions" in e for e in errors)


def test_validate_backup_positions_no_es_lista():
    data = {"version": BACKUP_VERSION, "positions": {"mal": "tipo"}}
    errors = validate_backup(data)
    assert any("lista" in e for e in errors)


def test_validate_backup_no_es_dict():
    errors = validate_backup("esto no es un dict")
    assert errors == ["El fichero no es un objeto JSON válido"]


# ---------------------------------------------------------------------------
#  ImportResult
# ---------------------------------------------------------------------------

def test_import_result_valores_iniciales():
    r = ImportResult()
    assert r.positions_found == 0
    assert r.positions_skipped == 0
    assert r.transactions_added == 0
    assert r.dividends_added == 0
    assert r.errors == []


def test_import_result_to_dict():
    r = ImportResult(positions_found=3, transactions_added=7, errors=["fallo"])
    d = r.to_dict()
    assert d["positions_found"] == 3
    assert d["transactions_added"] == 7
    assert d["positions_skipped"] == 0
    assert d["dividends_added"] == 0
    assert d["errors"] == ["fallo"]
