"""v1.6.17 - add last_login_at to users

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-06-01

Añade la columna last_login_at (DATETIME nullable) a la tabla users.
Se actualiza en cada login exitoso para mostrar la fecha de último acceso
en el panel de administración.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "b2c3d4e5f6a1"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("last_login_at", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("last_login_at")
