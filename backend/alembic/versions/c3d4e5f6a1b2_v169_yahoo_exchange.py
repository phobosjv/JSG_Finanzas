"""v1.6.19 - add yahoo_exchange to markets

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-06-01

Añade la columna yahoo_exchange (VARCHAR nullable) a la tabla markets.
Permite asociar cada mercado del catálogo con su código de exchange en
Yahoo Finance (ej. MCE=Madrid, NMS=NasdaqGS, LSE=Londres) para filtrar
búsquedas del explorador de valores.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "c3d4e5f6a1b2"
down_revision = "b2c3d4e5f6a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("markets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("yahoo_exchange", sa.String(20), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("markets", schema=None) as batch_op:
        batch_op.drop_column("yahoo_exchange")
