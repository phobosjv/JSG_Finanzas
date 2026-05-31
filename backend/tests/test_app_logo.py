"""
test_app_logo.py
================
Tests del logotipo configurable de la aplicación (v1.6.13).

Cubre:
- Subida del logo por admin (PUT /admin/config/logo) y persistencia.
- Endpoint público GET /config/logo (bytes + Content-Type).
- GET /config expone has_logo / logo_updated_at.
- Borrado (DELETE) revierte a estado sin logo.
- Permisos: usuario normal no puede subir ni borrar (403).
- Validación: mime no permitido, base64 inválido y tamaño > 1 MB → 422.
- data-URI aceptado (mime derivado del prefijo).
- Manifest dinámico /manifest.webmanifest: iconos por defecto vs logo.
"""

from __future__ import annotations

import base64

# PNG 1x1 transparente válido (firma 0x89 'PNG').
_PNG_1x1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_PNG_1x1_BYTES = base64.b64decode(_PNG_1x1_B64)


def _put_logo(client, data=_PNG_1x1_B64, mime="image/png"):
    return client.put("/api/admin/config/logo", json={"data": data, "mime": mime})


# ---------------------------------------------------------------------------
#  Subida y consulta
# ---------------------------------------------------------------------------

def test_admin_sube_logo_y_se_sirve(admin_client):
    resp = _put_logo(admin_client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_logo"] is True
    assert body["logo_updated_at"]

    # /config público refleja el logo
    cfg = admin_client.get("/api/config").json()
    assert cfg["has_logo"] is True
    assert cfg["logo_updated_at"] == body["logo_updated_at"]

    # /config/logo devuelve los bytes exactos con el Content-Type correcto
    logo = admin_client.get("/api/config/logo")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert logo.content == _PNG_1x1_BYTES


def test_logo_no_configurado_da_404(admin_client):
    # Sin subir nada todavía
    cfg = admin_client.get("/api/config").json()
    assert cfg["has_logo"] is False
    assert cfg["logo_updated_at"] is None
    assert admin_client.get("/api/config/logo").status_code == 404


def test_admin_borra_logo(admin_client):
    _put_logo(admin_client)
    assert admin_client.get("/api/config/logo").status_code == 200

    resp = admin_client.delete("/api/admin/config/logo")
    assert resp.status_code == 204

    assert admin_client.get("/api/config").json()["has_logo"] is False
    assert admin_client.get("/api/config/logo").status_code == 404


def test_data_uri_aceptado_sin_mime(admin_client):
    data_uri = f"data:image/png;base64,{_PNG_1x1_B64}"
    resp = _put_logo(admin_client, data=data_uri, mime=None)
    assert resp.status_code == 200
    logo = admin_client.get("/api/config/logo")
    assert logo.headers["content-type"] == "image/png"
    assert logo.content == _PNG_1x1_BYTES


# ---------------------------------------------------------------------------
#  Permisos
# ---------------------------------------------------------------------------

def test_subir_logo_requiere_admin(auth_client):
    assert _put_logo(auth_client).status_code == 403


def test_borrar_logo_requiere_admin(auth_client):
    assert auth_client.delete("/api/admin/config/logo").status_code == 403


# ---------------------------------------------------------------------------
#  Validación
# ---------------------------------------------------------------------------

def test_mime_no_permitido(admin_client):
    assert _put_logo(admin_client, mime="image/gif").status_code == 422


def test_base64_invalido(admin_client):
    assert _put_logo(admin_client, data="esto no es base64 %%%").status_code == 422


def test_imagen_demasiado_grande(admin_client):
    # 1 MiB + 1 byte → supera el límite LOGO_MAX_BYTES
    big = base64.b64encode(b"\x00" * (1024 * 1024 + 1)).decode("ascii")
    assert _put_logo(admin_client, data=big).status_code == 422


# ---------------------------------------------------------------------------
#  Manifest dinámico
# ---------------------------------------------------------------------------

def test_manifest_iconos_por_defecto(client):
    resp = client.get("/manifest.webmanifest")
    assert resp.status_code == 200
    data = resp.json()
    srcs = [i["src"] for i in data["icons"]]
    assert "/icons/icon-192.png" in srcs
    assert "/icons/icon-512.png" in srcs


def test_manifest_usa_logo_cuando_existe(admin_client):
    _put_logo(admin_client)
    data = admin_client.get("/manifest.webmanifest").json()
    srcs = [i["src"] for i in data["icons"]]
    assert all(s.startswith("/api/config/logo") for s in srcs)
    # El nombre del manifest sale de app_config (app_name) — por defecto JSG Soft.
    assert data["name"]
