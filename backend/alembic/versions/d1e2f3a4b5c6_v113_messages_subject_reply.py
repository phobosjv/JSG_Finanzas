"""v1.13.0 — añadir subject, admin_reply y admin_reply_at a catalog_messages.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_messages",
        sa.Column("subject", sa.Text, nullable=False, server_default=""),
    )
    op.add_column(
        "catalog_messages",
        sa.Column("admin_reply", sa.Text, nullable=True),
    )
    op.add_column(
        "catalog_messages",
        sa.Column("admin_reply_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_messages", "admin_reply_at")
    op.drop_column("catalog_messages", "admin_reply")
    op.drop_column("catalog_messages", "subject")
