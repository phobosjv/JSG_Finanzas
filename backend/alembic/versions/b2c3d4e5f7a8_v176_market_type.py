"""v1.7.6 - add market_type to markets

Revision ID: b2c3d4e5f7a8
Revises: a1b2c3d4e5f7
Create Date: 2026-06-02

Añade la columna market_type ('stock'|'fund'|'etf'|'crypto') a markets, base de
la segmentación por tipo de producto. Rellena automáticamente según los datos
actuales: fondos → 'fund'; código con 'etf' → 'etf'; con 'crypto' → 'crypto';
el resto → 'stock'. El admin puede corregir el tipo después.
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f7a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "markets",
        sa.Column("market_type", sa.String(), nullable=False, server_default="stock"),
    )
    op.execute(
        """
        UPDATE markets SET market_type = CASE
            WHEN is_fund_market = 1            THEN 'fund'
            WHEN lower(code) LIKE '%etf%'      THEN 'etf'
            WHEN lower(code) LIKE '%crypto%'   THEN 'crypto'
            ELSE 'stock'
        END
        """
    )
    with op.batch_alter_table("markets") as batch_op:
        batch_op.create_check_constraint(
            "ck_market_type", "market_type IN ('stock','fund','etf','crypto')"
        )


def downgrade() -> None:
    with op.batch_alter_table("markets") as batch_op:
        batch_op.drop_constraint("ck_market_type", type_="check")
        batch_op.drop_column("market_type")
