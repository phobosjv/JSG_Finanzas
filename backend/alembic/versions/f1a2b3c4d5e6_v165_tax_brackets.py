"""v1.6.5 - add tax_brackets table

Revision ID: f1a2b3c4d5e6
Revises: e3f1a2b4c5d6
Create Date: 2026-05-29

Crea la tabla tax_brackets para almacenar los tramos del IRPF del ahorro
de forma configurable desde el panel de administración.

Se inicializan los 5 tramos vigentes en España desde 2023:
  0 – 6.000 €      → 19 %
  6.000 – 50.000   → 21 %
  50.000 – 200.000 → 23 %
  200.000 – 300.000 → 27 %
  > 300.000         → 28 %
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e3f1a2b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tax_brackets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("min_amount", sa.REAL, nullable=False),
        sa.Column("max_amount", sa.REAL, nullable=True),
        sa.Column("rate", sa.REAL, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    # Tramos vigentes como datos iniciales
    op.execute("INSERT INTO tax_brackets (min_amount, max_amount, rate, sort_order) VALUES (0.0, 6000.0, 19.0, 0)")
    op.execute("INSERT INTO tax_brackets (min_amount, max_amount, rate, sort_order) VALUES (6000.0, 50000.0, 21.0, 1)")
    op.execute("INSERT INTO tax_brackets (min_amount, max_amount, rate, sort_order) VALUES (50000.0, 200000.0, 23.0, 2)")
    op.execute("INSERT INTO tax_brackets (min_amount, max_amount, rate, sort_order) VALUES (200000.0, 300000.0, 27.0, 3)")
    op.execute("INSERT INTO tax_brackets (min_amount, max_amount, rate, sort_order) VALUES (300000.0, NULL, 28.0, 4)")


def downgrade() -> None:
    op.drop_table("tax_brackets")
