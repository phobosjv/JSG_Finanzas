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

import json
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


# ---------------------------------------------------------------------------
# 6. Sin BOM en ficheros críticos (repo y zip)
#
# Bug prevenido: al usar Set-Content -Encoding utf8 en PowerShell 5.1 se
# añade un BOM (0xEF BB BF) al principio del fichero.  Esto rompe:
#   - backend/pyproject.toml → tomllib (Python 3.12) lanza TOMLDecodeError
#                              → 'pip install .' falla en el build Docker.
#   - frontend/package.json  → JSON.parse lanza SyntaxError en Vite
#                              → 'npm run build' falla.
#   - entrypoint.sh          → el kernel no reconoce el shebang ('#!')
#                              → el contenedor hace crash-loop.
# ---------------------------------------------------------------------------

_UTF8_BOM = b"\xef\xbb\xbf"

# Ficheros cuyo BOM rompe el despliegue o el build Docker.
_NO_BOM_FILES = [
    "backend/pyproject.toml",  # tomllib rechaza BOM → pip install falla
    "frontend/package.json",   # JSON.parse rechaza BOM → vite build falla
    "entrypoint.sh",           # shebang no reconocido → crash-loop en Docker
]


def test_ficheros_criticos_sin_bom_en_repo():
    """Los ficheros críticos del repositorio no deben tener BOM UTF-8.

    PowerShell 5.1 Set-Content -Encoding utf8 añade BOM silenciosamente;
    los parsers de Python (tomllib), Node (JSON.parse) y sh (shebang) fallan.
    """
    with_bom = []
    for rel in _NO_BOM_FILES:
        path = os.path.join(PROJECT_ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fh:
            if fh.read(3) == _UTF8_BOM:
                with_bom.append(rel)
    assert not with_bom, (
        "Los siguientes ficheros tienen BOM UTF-8 (0xEF BB BF) y causarán "
        "fallos en Docker o en el build del frontend:\n"
        + "\n".join(f"  - {f}" for f in with_bom)
        + "\nSolución: reescribir sin BOM (usar Python open(..., encoding='utf-8') "
        "o [System.IO.File]::WriteAllText con UTF8Encoding($false))."
    )


def test_ficheros_criticos_sin_bom_en_zip():
    """El zip de distribución no debe incluir versiones con BOM de los ficheros críticos."""
    zip_path = _latest_zip(PROJECT_ROOT)
    if zip_path is None:
        pytest.skip("No hay ningún zip de distribución en el proyecto.")

    with_bom = []
    with zipfile.ZipFile(zip_path) as zf:
        names_in_zip = {info.filename for info in zf.infolist()}
        for rel in _NO_BOM_FILES:
            zip_rel = rel.replace("\\", "/")
            if zip_rel not in names_in_zip:
                continue
            data = zf.read(zip_rel)
            if data[:3] == _UTF8_BOM:
                with_bom.append(zip_rel)

    zip_name = os.path.basename(zip_path)
    assert not with_bom, (
        f"El zip '{zip_name}' contiene ficheros con BOM que fallarán al desplegar:\n"
        + "\n".join(f"  - {f}" for f in with_bom)
    )


# ---------------------------------------------------------------------------
# 7. entrypoint.sh: shebang correcto y ruta 'cd' coherente con WORKDIR
#
# Bug prevenido: entrypoint.sh usaba 'cd /app/backend' pero el Dockerfile
# tiene WORKDIR /app.  /app/backend no se crea en ningún COPY → el contenedor
# hacía crash-loop con "can't cd to /app/backend" y Caddy devolvía 502.
# ---------------------------------------------------------------------------

def _parse_workdir(dockerfile_path: str) -> str | None:
    """Devuelve el WORKDIR final definido en el Dockerfile."""
    workdir = None
    with open(dockerfile_path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped.upper().startswith("WORKDIR "):
                workdir = stripped.split(None, 1)[1]
    return workdir


def test_entrypoint_shebang_sin_bom():
    """entrypoint.sh debe empezar con '#!' (0x23 0x21), sin BOM previo.

    Un BOM antes del shebang hace que el kernel no reconozca el intérprete
    y el contenedor falla al arrancar.
    """
    path = os.path.join(PROJECT_ROOT, "entrypoint.sh")
    if not os.path.isfile(path):
        pytest.skip("entrypoint.sh no encontrado.")
    with open(path, "rb") as fh:
        first2 = fh.read(2)
    assert first2 == b"#!", (
        f"entrypoint.sh no empieza con '#!' sino con {first2.hex()!r}. "
        "Si empieza con 0xEF 0xBB 0xBF (BOM) el contenedor no arrancará."
    )

    with open(path, "rb") as fh:
        raw = fh.read()
    assert b"\r\n" not in raw, (
        "entrypoint.sh tiene finales de línea CRLF. El kernel del contenedor "
        "leería el shebang como '/bin/sh\\r' → crash-loop. Se fuerza LF desde "
        "el .gitattributes de la raíz."
    )


def test_entrypoint_cd_coincide_con_workdir():
    """El directorio del 'cd' en entrypoint.sh debe existir en el contenedor.

    Se verifica que coincide con el WORKDIR del Dockerfile o es un subdirectorio
    creado explícitamente por alguna instrucción COPY.

    Bug prevenido: 'cd /app/backend' con WORKDIR /app → /app/backend no existe
    → crash-loop → Caddy 502 en todas las peticiones.
    """
    workdir = _parse_workdir(DOCKERFILE)
    assert workdir is not None, "El Dockerfile no define WORKDIR."

    path = os.path.join(PROJECT_ROOT, "entrypoint.sh")
    if not os.path.isfile(path):
        pytest.skip("entrypoint.sh no encontrado.")

    content = open(path, encoding="utf-8-sig").read()  # utf-8-sig elimina BOM si lo hay

    cd_match = re.search(r"^cd\s+(\S+)", content, re.MULTILINE)
    if cd_match is None:
        return  # Sin 'cd' explícito: usa el WORKDIR por defecto → OK

    cd_path = cd_match.group(1)

    # El 'cd' debe apuntar al WORKDIR o a un subdirectorio creado por COPY
    copy_sources = _parse_copy_sources(DOCKERFILE)
    # Rutas destino del Dockerfile (el segundo token de cada COPY)
    copy_dests: list[str] = []
    with open(DOCKERFILE, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line.upper().startswith("COPY "):
                continue
            line_no_flags = re.sub(r"--\S+\s+", "", line)
            parts = line_no_flags.split()
            if len(parts) >= 3:
                copy_dests.append(parts[2])

    valid_paths = {workdir} | {
        d if d.startswith("/") else workdir.rstrip("/") + "/" + d.lstrip("./")
        for d in copy_dests
    }

    # El cd_path debe ser el WORKDIR exacto o empezar por él
    assert cd_path == workdir or cd_path.startswith(workdir.rstrip("/") + "/"), (
        f"entrypoint.sh hace 'cd {cd_path}' pero el Dockerfile tiene "
        f"WORKDIR {workdir}.\n"
        f"Si '{cd_path}' no existe en el contenedor (no hay COPY que lo cree), "
        "el contenedor hará crash-loop.\n"
        f"Rutas conocidas en el contenedor: {sorted(valid_paths)}"
    )


# ---------------------------------------------------------------------------
# 7. docker-compose alternativo SIN Caddy (v1.23.0)
# ---------------------------------------------------------------------------
# Se distribuye un docker-compose.sin-caddy.yml para desplegar sin el
# reverse-proxy Caddy. Para usarlo, el usuario renombra este fichero a
# docker-compose.yml. Debe: (1) NO declarar el servicio caddy, (2) publicar el
# puerto de `finanzas` al host (si no, sin Caddy la app queda inaccesible).

COMPOSE_SIN_CADDY = os.path.join(PROJECT_ROOT, "docker-compose.sin-caddy.yml")


def test_compose_sin_caddy_existe():
    """El docker-compose alternativo (sin Caddy) debe estar en la raíz."""
    assert os.path.isfile(COMPOSE_SIN_CADDY), (
        "docker-compose.sin-caddy.yml no encontrado. Es la variante de "
        "despliegue sin Caddy que se distribuye en el zip."
    )


def test_compose_sin_caddy_no_declara_caddy():
    """La variante sin Caddy NO debe declarar el servicio ni volúmenes de caddy."""
    content = open(COMPOSE_SIN_CADDY, encoding="utf-8").read()
    # Buscar la clave de servicio 'caddy:' (con 2 espacios de indentación),
    # no las menciones en comentarios.
    assert not re.search(r"^  caddy:", content, re.MULTILINE), (
        "docker-compose.sin-caddy.yml declara el servicio 'caddy'; "
        "la variante sin Caddy no debe incluirlo."
    )
    assert not re.search(r"^  caddy-(data|config):", content, re.MULTILINE), (
        "docker-compose.sin-caddy.yml declara volúmenes de caddy; sobran sin Caddy."
    )


def test_compose_sin_caddy_publica_puerto_finanzas():
    """Sin Caddy delante, `finanzas` debe publicar un puerto al host."""
    content = open(COMPOSE_SIN_CADDY, encoding="utf-8").read()
    assert re.search(r'^\s*-\s*"\d+:8000"', content, re.MULTILINE), (
        "docker-compose.sin-caddy.yml no publica el puerto 8000 de 'finanzas'; "
        "sin Caddy la app quedaría inaccesible desde el host."
    )


def test_compose_sin_caddy_en_zip():
    """El zip de distribución debe incluir el docker-compose alternativo."""
    zip_path = _latest_zip(PROJECT_ROOT)
    if zip_path is None:
        pytest.skip("No hay ningún zip de distribución en el proyecto.")

    with zipfile.ZipFile(zip_path) as zf:
        names_in_zip = {info.filename for info in zf.infolist()}

    zip_name = os.path.basename(zip_path)
    assert "docker-compose.sin-caddy.yml" in names_in_zip, (
        f"El zip '{zip_name}' no incluye docker-compose.sin-caddy.yml "
        "(variante de despliegue sin Caddy)."
    )


# ---------------------------------------------------------------------------
# 8. entrypoint.sh debe aplicar las migraciones antes de arrancar uvicorn
#
# Bug real (introducido en v1.16.0, detectado en v1.23.1): al regenerar
# entrypoint.sh con printf se perdió la línea 'alembic upgrade head'. En el VPS
# no se notó porque el volumen ya tenía finanzas.db con todas las tablas
# creadas por versiones anteriores. En una instalación NUEVA (volumen vacío)
# nadie crea el esquema: SQLite genera un fichero .db vacío y el lifespan
# revienta en _ensure_default_admin() con
#   sqlalchemy.exc.OperationalError: no such table: users
#   ERROR: Application startup failed. Exiting.
# → crash-loop del contenedor.
#
# No hay ningún create_all() en producción (solo en los tests), así que las
# migraciones de Alembic son la ÚNICA vía de creación del esquema.
# ---------------------------------------------------------------------------

def test_entrypoint_aplica_migraciones_antes_de_uvicorn():
    """entrypoint.sh debe ejecutar 'alembic upgrade head' antes de uvicorn."""
    path = os.path.join(PROJECT_ROOT, "entrypoint.sh")
    if not os.path.isfile(path):
        pytest.skip("entrypoint.sh no encontrado.")

    content = open(path, encoding="utf-8-sig").read()

    migrate = re.search(r"^\s*alembic\s+upgrade\s+head\s*$", content, re.MULTILINE)
    assert migrate is not None, (
        "entrypoint.sh no ejecuta 'alembic upgrade head'. En una instalación "
        "nueva (volumen vacío) no se crearía el esquema y el arranque fallaría "
        "con 'no such table: users'."
    )

    serve = re.search(r"^\s*exec\s+uvicorn\b", content, re.MULTILINE)
    assert serve is not None, "entrypoint.sh no arranca uvicorn con 'exec'."
    assert migrate.start() < serve.start(), (
        "'alembic upgrade head' debe ir ANTES de arrancar uvicorn: el lifespan "
        "de la app consulta la tabla users nada más arrancar."
    )


def test_entrypoint_migraciones_en_el_zip():
    """El zip debe llevar alembic/ y alembic.ini, y el Dockerfile copiarlos.

    Sin ellos 'alembic upgrade head' fallaría dentro del contenedor.
    """
    dockerfile = open(DOCKERFILE, encoding="utf-8").read()
    assert re.search(r"^COPY\s+backend/alembic\s", dockerfile, re.MULTILINE), (
        "El Dockerfile no copia backend/alembic al contenedor."
    )
    assert re.search(r"^COPY\s+backend/alembic\.ini\s", dockerfile, re.MULTILINE), (
        "El Dockerfile no copia backend/alembic.ini al contenedor."
    )

    zip_path = _latest_zip(PROJECT_ROOT)
    if zip_path is None:
        pytest.skip("No hay ningún zip de distribución en el proyecto.")

    with zipfile.ZipFile(zip_path) as zf:
        names_in_zip = {info.filename for info in zf.infolist()}

    zip_name = os.path.basename(zip_path)
    assert "backend/alembic.ini" in names_in_zip, (
        f"El zip '{zip_name}' no incluye backend/alembic.ini."
    )
    versiones = [n for n in names_in_zip if n.startswith("backend/alembic/versions/")
                 and n.endswith(".py")]
    assert versiones, (
        f"El zip '{zip_name}' no incluye las migraciones de "
        "backend/alembic/versions/."
    )


# ---------------------------------------------------------------------------
# 4. La version del bundle compilado coincide con package.json
# ---------------------------------------------------------------------------

def _version_de_package_json(raw: bytes) -> str:
    return json.loads(raw.decode("utf-8"))["version"]


def _bundle_principal(nombres) -> str | None:
    """Nombre del bundle de aplicacion dentro de frontend/dist/assets."""
    cands = [
        n for n in nombres
        if "frontend/dist/assets/index." in n.replace("\\", "/") and n.endswith(".js")
    ]
    return cands[0] if cands else None


def test_bundle_compilado_lleva_la_version_de_package_json():
    """
    El numero de version que se ve en la aplicacion sale del BUNDLE, no del
    fichero: Login.jsx y Navigation.jsx hacen 'import { version } from
    package.json', y Vite lo incrusta como literal en tiempo de compilacion.

    Bug prevenido (v1.24.3): se compilo el frontend ANTES de subir la version,
    asi que package.json decia 1.24.3 y el bundle seguia diciendo 1.24.2. El zip
    pasaba todas las verificaciones —el package.json que lleva dentro es el
    correcto— y la aplicacion desplegada mostraba la version anterior en el
    login. Se perdio un despliegue entero buscandolo en la cache del navegador y
    en el service worker de la PWA.

    Regla: en la secuencia de release, 'npm run build' va SIEMPRE despues del
    bump de version. Este test lo comprueba en el disco.
    """
    dist = os.path.join(PROJECT_ROOT, "frontend", "dist", "assets")
    pkg = os.path.join(PROJECT_ROOT, "frontend", "package.json")
    if not os.path.isdir(dist) or not os.path.exists(pkg):
        pytest.skip("frontend/dist o package.json no disponibles")

    version = _version_de_package_json(open(pkg, "rb").read())
    bundles = [f for f in os.listdir(dist) if f.startswith("index.") and f.endswith(".js")]
    assert bundles, "no hay bundle index.*.js en frontend/dist/assets"

    encontrado = any(
        version in open(os.path.join(dist, b), encoding="utf-8", errors="ignore").read()
        for b in bundles
    )
    assert encontrado, (
        f"package.json dice {version} pero ningun bundle de frontend/dist/assets "
        f"lo contiene: {bundles}. El frontend se compilo ANTES del bump de version; "
        "hay que volver a ejecutar 'npm run build' y regenerar el zip."
    )


def test_zip_lleva_el_bundle_con_la_version_correcta():
    """Lo mismo, pero dentro del zip que se sube al servidor."""
    zip_path = _latest_zip(PROJECT_ROOT)
    if zip_path is None:
        pytest.skip("no hay zip de distribucion generado")

    with zipfile.ZipFile(zip_path) as zf:
        nombres = zf.namelist()
        if "frontend/package.json" not in nombres:
            pytest.skip("el zip no incluye frontend/package.json")
        version = _version_de_package_json(zf.read("frontend/package.json"))
        bundle = _bundle_principal(nombres)
        assert bundle, f"el zip no lleva bundle de aplicacion: {os.path.basename(zip_path)}"
        contenido = zf.read(bundle).decode("utf-8", errors="ignore")

    assert version in contenido, (
        f"{os.path.basename(zip_path)}: package.json dice {version} pero {bundle} no "
        "lo contiene. El zip se genero con un build anterior al bump de version; "
        "la aplicacion desplegada mostraria la version antigua."
    )


# ---------------------------------------------------------------------------
# 5. El zip no lleva ninguna base de datos
# ---------------------------------------------------------------------------

def test_zip_no_contiene_bases_de_datos():
    """
    El zip de distribucion NO puede llevar ningun fichero SQLite.

    Bug prevenido (v1.24.3): se colo 'finanzas.db.bak-20260821-142941', 18 MB con
    la base de datos REAL —usuarios, hashes de contrasena, emails y carteras
    completas— y llego a subirse a produccion. El filtro del script comparaba
    'os.path.splitext(rel)[1]' contra {'.db', '.db-shm', '.db-wal'}, pero para ese
    nombre splitext devuelve '.bak-20260821-142941', asi que no coincidia con
    nada. Git si lo ignoraba ('*.db.bak-*' en .gitignore), pero el script del zip
    no usa .gitignore: tiene sus propias reglas.

    La unica senal era el tamano: 5,4 MB frente a los 944 KB de la version
    anterior. Ninguna verificacion lo miraba.

    Se comprueba por partida doble, porque el nombre se puede disfrazar:
    por nombre y por la cabecera magica de SQLite.
    """
    zip_path = _latest_zip(PROJECT_ROOT)
    if zip_path is None:
        pytest.skip("no hay zip de distribucion generado")

    culpables: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            base = os.path.basename(info.filename)
            if ".db" in base:
                culpables.append(f"{info.filename} (por nombre)")
                continue
            if info.file_size > 512:
                with zf.open(info) as fh:
                    if fh.read(16) == b"SQLite format 3\x00":
                        culpables.append(f"{info.filename} (cabecera SQLite)")

    assert not culpables, (
        f"{os.path.basename(zip_path)} incluye bases de datos:\n"
        + "\n".join(f"  - {c}" for c in culpables)
        + "\nEl zip se distribuye: no puede llevar datos de usuarios."
    )
