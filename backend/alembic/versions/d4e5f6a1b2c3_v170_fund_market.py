"""v1.7.0 - add is_fund_market to markets

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-06-01

Añade la columna is_fund_market (BOOLEAN, default False) a la tabla markets.
Los mercados de fondos de inversión se marcan con este flag:
- Se excluyen del informe fiscal PDF (la retención la gestiona la entidad).
- El catálogo import/export incluye este campo.
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a1b2c3"
down_revision = "c3d4e5f6a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("markets") as batch_op:
        batch_op.add_column(
            sa.Column("is_fund_market", sa.Boolean(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("markets") as batch_op:
        batch_op.drop_column("is_fund_market")
