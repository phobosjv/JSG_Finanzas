"""v1.12.0 — solicitudes de usuario para agregar productos al catálogo,
notificaciones in-app y mensajes al administrador.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("isin", sa.Text, nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "market_id",
            sa.Text,
            sa.ForeignKey("markets.code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("currency", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column(
            "security_id",
            sa.Integer,
            sa.ForeignKey("securities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
    )
    op.create_index("idx_security_requests_user", "security_requests", ["user_id"])
    op.create_index("idx_security_requests_status", "security_requests", ["status"])

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("related_id", sa.Integer, nullable=True),
        sa.Column("related_type", sa.Text, nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
    )
    op.create_index("idx_user_notifications_user", "user_notifications", ["user_id"])

    op.create_table(
        "catalog_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column(
            "security_request_id",
            sa.Integer,
            sa.ForeignKey("security_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
    )
    op.create_index("idx_catalog_messages_user", "catalog_messages", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_catalog_messages_user", table_name="catalog_messages")
    op.drop_table("catalog_messages")
    op.drop_index("idx_user_notifications_user", table_name="user_notifications")
    op.drop_table("user_notifications")
    op.drop_index("idx_security_requests_status", table_name="security_requests")
    op.drop_index("idx_security_requests_user", table_name="security_requests")
    op.drop_table("security_requests")
