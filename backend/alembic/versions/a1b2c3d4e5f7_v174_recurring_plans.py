"""v1.7.4 - tabla recurring_plans (aportaciones periódicas futuras)

Revision ID: a1b2c3d4e5f7
Revises: f6a1b2c3d4e5
Create Date: 2026-06-02

Crea la tabla recurring_plans: planes de aportaciones periódicas (DCA) hacia el
futuro. El scheduler crea las compras cuando llega cada fecha (usando el precio
real de ese día). Las aportaciones pasadas se registran como compras directas y
NO viven en esta tabla.
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "f6a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "position_id", sa.Integer(),
            sa.ForeignKey("positions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("amount_per_period", sa.Float(), nullable=False),
        sa.Column("fee_per_period", sa.Float(), nullable=False, server_default="0"),
        sa.Column("frequency", sa.String(), nullable=False),
        sa.Column("start_date", sa.String(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("done_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.String(), nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.CheckConstraint(
            "frequency IN ('weekly','monthly','quarterly','yearly')",
            name="ck_recplan_frequency",
        ),
    )
    op.create_index("idx_recplan_position", "recurring_plans", ["position_id"])


def downgrade() -> None:
    op.drop_index("idx_recplan_position", table_name="recurring_plans")
    op.drop_table("recurring_plans")
