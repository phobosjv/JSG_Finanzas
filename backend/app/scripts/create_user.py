"""
scripts/create_user.py
======================
Crea un usuario en la base de datos.

Uso:
    cd backend
    python -m app.scripts.create_user <username> <password> [--admin]

Útil para el primer arranque (no hay endpoint de registro público)
y para recuperar el acceso si se pierde la contraseña.

El flag --admin crea el usuario con permisos de administrador.
"""

import sys


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--admin"]
    is_admin = "--admin" in sys.argv[1:]

    if len(args) != 2:
        print("Uso: python -m app.scripts.create_user <username> <password> [--admin]")
        sys.exit(1)

    username, password = args[0], args[1]

    if len(password) < 8:
        print("Error: la contraseña debe tener al menos 8 caracteres")
        sys.exit(1)

    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import User
    from app.auth.security import hash_password

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            print(f"Error: el usuario '{username}' ya existe")
            sys.exit(1)

        user = User(
            username=username,
            password_hash=hash_password(password),
            is_admin=is_admin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        role = "administrador" if is_admin else "usuario"
        print(f"{role.capitalize()} '{username}' creado con id={user.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
