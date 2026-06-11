"""v1.17.0 — añadir max_2y y max_5y a price_snapshots.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_snapshots",
        sa.Column("max_2y", sa.Float, nullable=True),
    )
    op.add_column(
        "price_snapshots",
        sa.Column("max_5y", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_snapshots", "max_5y")
    op.drop_column("price_snapshots", "max_2y")
