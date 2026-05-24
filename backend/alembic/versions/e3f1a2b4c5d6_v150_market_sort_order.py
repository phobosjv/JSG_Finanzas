"""v1.5.0 - add sort_order to markets

Revision ID: e3f1a2b4c5d6
Revises: b2d1a3c4e5f6
Create Date: 2026-05-24

Añade sort_order (INTEGER, default 0) a la tabla markets para que el
administrador pueda controlar el orden de las pestañas en la UI.
Los mercados existentes se inicializan con sort_order = 0 (orden actual
por code se mantiene mientras no se reordenen explícitamente).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3f1a2b4c5d6"
down_revision = "b2d1a3c4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "markets",
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("markets", "sort_order")
