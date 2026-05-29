"""
test_distribution.py
====================
Verifica la coherencia entre el Dockerfile y el repositorio para que
'docker-compose up --build' no falle por archivos ausentes.

Bug prevenido
-------------
v1.6.2: el Dockerfile ejecuta 'pip install .' que lee
backend/pyproject.toml, pero ese fichero no estaba incluido en el zip
de distribución. El build Docker fallaba con:

    COPY failed: file not found in build context or excluded by .dockerignore:
    stat backend/pyproject.toml: file does not exist

Los tests de esta suite comprueban:
  1. Que cada path fuente de una instrucción COPY del Dockerfile existe
     en el repositorio (en disco, no en el zip).
  2. Que backend/pyproject.toml tiene la estructura mínima que necesita
     'pip install .' para instalar las dependencias.
  3. Que el zip de distribución más reciente (si existe) contiene todos
     los paths fuente del Dockerfile.

Ejecutar:  pytest tests/test_distribution.py -v
"""

from __future__ import annotations

import os
import re
import zipfile

import pytest

# ---------------------------------------------------------------------------
# Helpers para localizar el proyecto
# ---------------------------------------------------------------------------

# tests/ está en backend/tests/; raíz del proyecto es dos niveles arriba
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCKERFILE = os.path.join(PROJECT_ROOT, "Dockerfile")


def _parse_copy_sources(dockerfile_path: str) -> list[str]:
    """Devuelve los paths fuente de todas las instrucciones COPY del Dockerfile.

    Maneja tanto 'COPY src dst' como 'COPY --chown=... src dst'.
    Ignora la directiva ADD (no usada en este proyecto).
    """
    sources: list[str] = []
    with open(dockerfile_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line.upper().startswith("COPY "):
                continue
            # Eliminar flags opcionales tipo --chown=... o --from=...
            line_no_flags = re.sub(r"--\S+\s+", "", line)
            parts = line_no_flags.split()
            # parts[0] == 'COPY', parts[1] == src, parts[2] == dst
            if len(parts) >= 3:
                sources.append(parts[1])
    return sources


def _latest_zip(project_root: str) -> str | None:
    """Devuelve el path al zip de distribución más reciente, o None si no existe."""
    zips = sorted(
        (
            os.path.join(project_root, f)
            for f in os.listdir(project_root)
            if re.match(r"finanzas-v\d+\.\d+\.\d+\.zip", f)
        ),
        reverse=True,
    )
    return zips[0] if zips else None


# ---------------------------------------------------------------------------
# 1. El Dockerfile existe y tiene instrucciones COPY
# ---------------------------------------------------------------------------

def test_dockerfile_existe():
    """El Dockerfile debe estar en la raíz del proyecto."""
    assert os.path.isfile(DOCKERFILE), (
        f"Dockerfile no encontrado en {PROJECT_ROOT}. "
        "Es necesario para docker-compose up --build."
    )


def test_dockerfile_tiene_instrucciones_copy():
    """El Dockerfile debe tener al menos una instrucción COPY."""
    sources = _parse_copy_sources(DOCKERFILE)
    assert sources, "El Dockerfile no contiene ninguna instrucción COPY."


# ---------------------------------------------------------------------------
# 2. Todos los paths fuente del Dockerfile existen en el repositorio
# ---------------------------------------------------------------------------

def test_dockerfile_copy_sources_existen():
    """Cada 'COPY src dst' del Dockerfile debe tener su src en el repositorio.

    Si falta alguno, 'docker-compose up --build' fallará con
    'COPY failed: file not found in build context'.
    """
    sources = _parse_copy_sources(DOCKERFILE)
    missing = [
        src
        for src in sources
        if not os.path.exists(os.path.join(PROJECT_ROOT, src))
    ]
    assert not missing, (
        "Los siguientes paths referenciados en el Dockerfile NO existen "
        "en el repositorio (el build Docker fallaría):\n"
        + "\n".join(f"  - {s}" for s in missing)
    )


# ---------------------------------------------------------------------------
# 3. pyproject.toml es válido para 'pip install .'
# ---------------------------------------------------------------------------

def test_pyproject_toml_existe():
    """backend/pyproject.toml es el manifiesto que lee 'pip install .'."""
    path = os.path.join(PROJECT_ROOT, "backend", "pyproject.toml")
    assert os.path.isfile(path), (
        "backend/pyproject.toml no existe. "
        "El Dockerfile ejecuta 'pip install .' que necesita este fichero."
    )


def test_pyproject_toml_tiene_seccion_project():
    """pyproject.toml debe tener [project] para que pip lo procese."""
    path = os.path.join(PROJECT_ROOT, "backend", "pyproject.toml")
    content = open(path, encoding="utf-8").read()
    assert "[project]" in content, (
        "pyproject.toml no tiene la sección [project]. "
        "'pip install .' no encontrará las dependencias."
    )


def test_pyproject_toml_tiene_dependencies():
    """pyproject.toml debe declarar 'dependencies' para instalar los paquetes."""
    path = os.path.join(PROJECT_ROOT, "backend", "pyproject.toml")
    content = open(path, encoding="utf-8").read()
    assert "dependencies" in content, (
        "pyproject.toml no declara 'dependencies'. "
        "El contenedor arrancará sin las dependencias necesarias."
    )


# ---------------------------------------------------------------------------
# 4. El zip de distribución contiene todos los paths del Dockerfile
# ---------------------------------------------------------------------------

def test_zip_contiene_sources_del_dockerfile():
    """El zip de distribución debe incluir todos los paths fuente del Dockerfile.

    Bug prevenido: en v1.6.2 faltaba backend/pyproject.toml en el zip,
    por lo que el build Docker fallaba aunque el fichero existía en el repo.
    """
    zip_path = _latest_zip(PROJECT_ROOT)
    if zip_path is None:
        pytest.skip("No hay ningún zip de distribución en el proyecto.")

    sources = _parse_copy_sources(DOCKERFILE)
    with zipfile.ZipFile(zip_path) as zf:
        names_in_zip = {info.filename for info in zf.infolist()}

    missing_from_zip: list[str] = []
    for src in sources:
        # Normalizar a formato zip (barras '/')
        src_zip = src.replace("\\", "/")
        # El src puede ser un fichero o un directorio; en el zip los
        # ficheros de un directorio aparecen como 'dir/fichero', no 'dir/'.
        # Basta con comprobar que hay al menos una entrada con ese prefijo.
        found = any(
            name == src_zip or name.startswith(src_zip.rstrip("/") + "/")
            for name in names_in_zip
        )
        if not found:
            missing_from_zip.append(src)

    zip_name = os.path.basename(zip_path)
    assert not missing_from_zip, (
        f"El zip '{zip_name}' no contiene los siguientes paths "
        "que el Dockerfile necesita (el build Docker fallaría al desplegar):\n"
        + "\n".join(f"  - {s}" for s in missing_from_zip)
    )


def test_zip_no_contiene_env_ni_claude():
    """El zip NO debe incluir .env (credenciales) ni CLAUDE.md (instrucciones internas)."""
    zip_path = _latest_zip(PROJECT_ROOT)
    if zip_path is None:
        pytest.skip("No hay ningún zip de distribución en el proyecto.")

    with zipfile.ZipFile(zip_path) as zf:
        names_in_zip = [info.filename for info in zf.infolist()]

    forbidden = [
        n for n in names_in_zip
        if n == "backend/.env"
        or n.endswith("/CLAUDE.md")
        or n == "CLAUDE.md"
    ]
    zip_name = os.path.basename(zip_path)
    assert not forbidden, (
        f"El zip '{zip_name}' contiene ficheros que NO deben distribuirse:\n"
        + "\n".join(f"  - {f}" for f in forbidden)
    )


# ---------------------------------------------------------------------------
# 5. Iconos PWA presentes y válidos (PNG)
# ---------------------------------------------------------------------------

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PWA_ICONS = [
    "frontend/public/icons/icon-192.png",
    "frontend/public/icons/icon-512.png",
]


def test_pwa_icons_existen_en_repo():
    """Los iconos PWA referenciados en vite.config.js deben existir en el repo.

    Bug prevenido: v1.6.6 — sin estos ficheros los navegadores no muestran
    el botón de instalación aunque VitePWA esté configurado.
    """
    missing = [
        icon for icon in _PWA_ICONS
        if not os.path.isfile(os.path.join(PROJECT_ROOT, icon))
    ]
    assert not missing, (
        "Los siguientes iconos PWA no existen en el repositorio "
        "(el botón de instalación no aparecerá en los navegadores):\n"
        + "\n".join(f"  - {i}" for i in missing)
    )


def test_pwa_icons_son_png_validos():
    """Los iconos PWA deben ser ficheros PNG válidos (firma correcta)."""
    for icon in _PWA_ICONS:
        path = os.path.join(PROJECT_ROOT, icon)
        if not os.path.isfile(path):
            pytest.skip(f"Icono no encontrado: {icon} (cubierto por test anterior)")
        with open(path, "rb") as fh:
            header = fh.read(8)
        assert header == _PNG_SIGNATURE, (
            f"{icon} no es un PNG válido. "
            f"Firma encontrada: {header.hex()!r} (esperada: {_PNG_SIGNATURE.hex()!r})"
        )


def test_pwa_icons_en_zip():
    """El zip de distribución debe incluir los iconos PWA compilados en dist/.

    Sin ellos el service worker no puede precachearlos y la instalación PWA
    falla en producción aunque funcione en desarrollo.
    """
    zip_path = _latest_zip(PROJECT_ROOT)
    if zip_path is None:
        pytest.skip("No hay ningún zip de distribución en el proyecto.")

    dist_icons = [
        icon.replace("frontend/public/", "frontend/dist/")
        for icon in _PWA_ICONS
    ]
    with zipfile.ZipFile(zip_path) as zf:
        names_in_zip = {info.filename for info in zf.infolist()}

    missing = [i for i in dist_icons if i not in names_in_zip]
    zip_name = os.path.basename(zip_path)
    assert not missing, (
        f"El zip '{zip_name}' no contiene los iconos PWA compilados:\n"
        + "\n".join(f"  - {i}" for i in missing)
    )
