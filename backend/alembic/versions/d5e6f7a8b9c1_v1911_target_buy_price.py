"""v1.9.11 — target_buy_price en positions

Revision ID: d5e6f7a8b9c1
Revises: c3d4e5f6a1b9
Create Date: 2026-06-05

Añade la columna target_buy_price (REAL, nullable) a la tabla positions,
simétrica a target_sell_price ya existente. Permite al usuario fijar un
precio de alerta de compra por posición.
"""

from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c1"
down_revision = "c3d4e5f6a1b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("positions", sa.Column("target_buy_price", sa.REAL(), nullable=True))


def downgrade() -> None:
    op.drop_column("positions", "target_buy_price")
