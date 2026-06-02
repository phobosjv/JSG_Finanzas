"""v1.7.2 - add transfer_group_id to transactions

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-06-02

Añade la columna transfer_group_id (VARCHAR, nullable) a transactions.

Un traspaso de fondos crea DOS filas acopladas (transfer_out en el origen,
transfer_in en el destino). Esta columna las vincula con un mismo identificador
de grupo para poder DESHACER el traspaso atómicamente (borrar ambas filas).

Las transacciones ordinarias (buy/sell) y los traspasos creados antes de esta
versión llevan NULL: no son anulables como pareja desde la UI.
"""

from alembic import op
import sqlalchemy as sa

revision = "f6a1b2c3d4e5"
down_revision = "e5f6a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column("transfer_group_id", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("transfer_group_id")
