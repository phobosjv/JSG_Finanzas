"""v1.4.0 - security_splits table

Revision ID: b2d1a3c4e5f6
Revises: c7f9e2b4d8a1
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2d1a3c4e5f6"
down_revision = "c7f9e2b4d8a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_splits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "security_id",
            sa.Integer,
            sa.ForeignKey("securities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ex_date", sa.String, nullable=False),
        sa.Column("ratio_num", sa.Integer, nullable=False),
        sa.Column("ratio_den", sa.Integer, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.datetime("now"),
            nullable=False,
        ),
        sa.CheckConstraint("ratio_num >= 1", name="ck_split_ratio_num_positive"),
        sa.CheckConstraint("ratio_den >= 1", name="ck_split_ratio_den_positive"),
    )
    op.create_index("idx_splits_security_id", "security_splits", ["security_id"])


def downgrade() -> None:
    op.drop_index("idx_splits_security_id", table_name="security_splits")
    op.drop_table("security_splits")
