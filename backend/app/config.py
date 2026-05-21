"""
config.py
=========
Settings de la aplicacion cargadas desde variables de entorno.

En produccion (Docker) las variables vienen del docker-compose.yml.
En desarrollo local se pueden poner en un fichero .env en la raiz de
'backend/'; pydantic-settings lo carga automaticamente si existe.

SECRET_KEY no tiene default: si no esta definida la app falla en el
arranque con un error claro, que es el comportamiento correcto en
produccion.  En desarrollo se puede poner en .env.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Base de datos
    database_url: str = "sqlite:///./finanzas.db"

    # Autenticacion (cookie de sesion firmada)
    secret_key: str  # requerido, sin default
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 dias

    # CORS: origenes permitidos.
    # En produccion Docker el frontend lo sirve el propio FastAPI (mismo origen),
    # por lo que CORS no es necesario. Solo importa si hay un reverse proxy
    # en un dominio distinto; en ese caso pasar ALLOWED_ORIGINS=["https://tu-dominio.com"].
    allowed_origins: list[str] = ["http://localhost:5173"]

    # Marca la cookie de sesion como Secure (solo HTTPS).
    # Poner a false en intranets o despliegues HTTP.
    cookie_secure: bool = False

    # Usuario administrador por defecto.
    # Si ADMIN_DEFAULT_USER está definido y ese usuario no existe en la BD,
    # se crea automáticamente al arrancar la aplicación.
    admin_default_user: str = "admin"
    admin_default_password: str = "admin1234"

    # Debug: activa reload de uvicorn y logs detallados
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """
    Instancia unica de Settings, cacheada.
    Inyectable via FastAPI Depends(get_settings).
    """
    return Settings()
