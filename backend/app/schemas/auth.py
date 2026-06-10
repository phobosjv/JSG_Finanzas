"""Schemas de autenticacion y administracion de usuarios."""
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("No puede estar vacio")
        return v


class UserOut(BaseModel):
    id: int
    username: str
    is_admin: bool

    model_config = {"from_attributes": True}


class UserAdminOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_enabled: bool
    expires_at: datetime | None
    created_at: datetime
    last_login_at: datetime | None = None
    has_operations: bool = False
    email: str | None = None

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False
    email: str | None = None

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("No puede estar vacío")
        if len(v) < 3:
            raise ValueError("Mínimo 3 caracteres")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Mínimo 8 caracteres")
        return v


class ChangePasswordRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Mínimo 8 caracteres")
        return v


class SelfChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Mínimo 8 caracteres")
        return v


class UserStatusIn(BaseModel):
    """Habilitar o deshabilitar un usuario, con anotacion opcional."""
    enabled: bool
    annotation: str | None = None


class UserExpiryIn(BaseModel):
    """Poner o borrar la fecha de caducidad de un usuario (solo fecha, sin hora)."""
    expires_at: date | None


class UserStatusLogOut(BaseModel):
    id: int
    status: str
    annotation: str | None
    created_at: datetime
    actor_username: str | None


class UserEmailIn(BaseModel):
    """Actualizar el email de un usuario (null para borrarlo)."""
    email: str | None = None
