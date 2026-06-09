"""v1.11.0 — subcarteras: agrupaciones personalizadas de posiciones por usuario

Revision ID: b9c0d1e2f3a4
Revises: f7a8b9c0d1e2
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa

revision = "b9c0d1e2f3a4"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subcarteras",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
    )
    op.create_index("idx_subcarteras_user", "subcarteras", ["user_id"])

    op.create_table(
        "subcartera_positions",
        sa.Column(
            "subcartera_id",
            sa.Integer,
            sa.ForeignKey("subcarteras.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "position_id",
            sa.Integer,
            sa.ForeignKey("positions.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("subcartera_positions")
    op.drop_index("idx_subcarteras_user", table_name="subcarteras")
    op.drop_table("subcarteras")
