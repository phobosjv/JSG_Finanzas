"""v1.10.0 — push_subscriptions para notificaciones Web Push

Revision ID: f7a8b9c0d1e2
Revises: d5e6f7a8b9c1
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "d5e6f7a8b9c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("endpoint", sa.Text, nullable=False, unique=True),
        sa.Column("p256dh", sa.Text, nullable=False),
        sa.Column("auth", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        sa.Column("last_notified_keys", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("push_subscriptions")
