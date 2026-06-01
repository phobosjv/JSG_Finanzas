"""v1.6.16 - remove currency check constraints for multi-currency support

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-01

Elimina los CHECK constraints que limitaban currency a 'EUR'|'USD' en las
tablas transactions y dividends, para permitir divisas adicionales
configuradas por el administrador (GBP, CHF, JPY, etc.).

SQLite no soporta DROP CONSTRAINT directamente, por lo que se usa
batch_alter_table (Alembic lo recrea internamente con la restricción eliminada).
"""
from __future__ import annotations

from alembic import op


revision = "a1b2c3d4e5f6"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Eliminar ck_tx_currency de la tabla transactions
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_tx_currency", type_="check")

    # Eliminar ck_div_currency de la tabla dividends
    with op.batch_alter_table("dividends", schema=None) as batch_op:
        batch_op.drop_constraint("ck_div_currency", type_="check")


def downgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_tx_currency", "currency IN ('EUR','USD')"
        )

    with op.batch_alter_table("dividends", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_div_currency", "currency IN ('EUR','USD')"
        )
