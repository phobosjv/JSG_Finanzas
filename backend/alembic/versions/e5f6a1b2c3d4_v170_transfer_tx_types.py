"""v1.7.0 - ampliar ck_tx_type con transfer_in / transfer_out

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-06-02

Amplía el CHECK constraint ck_tx_type de la tabla transactions para admitir
los tipos de traspaso de fondos:
  - transfer_in  : entrada de un traspaso (se comporta como compra, coste heredado)
  - transfer_out : salida de un traspaso (consume FIFO sin resultado fiscal)

SQLite no soporta ALTER CONSTRAINT; se usa batch_alter_table, que recrea la
tabla con el nuevo constraint preservando los datos.
"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6a1b2c3d4"
down_revision = "d4e5f6a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint("ck_tx_type", type_="check")
        batch_op.create_check_constraint(
            "ck_tx_type",
            "type IN ('buy','sell','transfer_in','transfer_out')",
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint("ck_tx_type", type_="check")
        batch_op.create_check_constraint(
            "ck_tx_type",
            "type IN ('buy','sell')",
        )
