"""
auth/security.py
================
Hash y verificacion de contrasenas con bcrypt (libreria nativa).

Se usa bcrypt directamente en lugar de passlib porque passlib 1.7
no es compatible con bcrypt >= 4.0 (el modulo __about__ fue eliminado
y el fallback de passlib produce secretos de >72 bytes que bcrypt
rechaza con ValueError).
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Devuelve el hash bcrypt de la contrasena en texto plano."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """True si 'plain' coincide con el hash almacenado."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def needs_rehash(hashed: str) -> bool:
    """
    True si el hash fue generado con un coste menor al actual por defecto.
    Permite actualizar hashes antiguos de forma transparente en el login.
    """
    # bcrypt.gensalt() usa rounds=12 por defecto; compara con el hash real.
    current_rounds = bcrypt.gensalt().decode().split("$")[3]
    stored_rounds  = hashed.split("$")[3] if hashed.startswith("$2") else ""
    return stored_rounds != current_rounds
