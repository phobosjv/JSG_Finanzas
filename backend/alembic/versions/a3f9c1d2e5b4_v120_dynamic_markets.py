"""v1.2.0 - dynamic markets and app_config

Revision ID: a3f9c1d2e5b4
Revises: 9b1c2b84199f
Create Date: 2026-05-23 09:12:23

Cambios:
  - Crea tabla 'markets' con los tres mercados por defecto.
  - Crea tabla 'app_config' con snapshot_interval_minutes=5.
  - Elimina el CheckConstraint 'ck_securities_market' de la tabla 'securities'
    (el mercado ahora es un string libre validado contra la tabla 'markets').
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f9c1d2e5b4'
down_revision: Union[str, None] = '9b1c2b84199f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tabla markets
    op.create_table(
        'markets',
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('index_ticker', sa.String(), nullable=True),
        sa.Column('currency', sa.String(), nullable=False, server_default='EUR'),
        sa.Column('fiscal_window_days', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('created_at', sa.String(), nullable=False,
                  server_default=sa.text("(datetime('now'))")),
        sa.PrimaryKeyConstraint('code'),
    )
    op.execute("""
        INSERT INTO markets (code, name, index_ticker, currency, fiscal_window_days)
        VALUES
            ('ibex35',  'IBEX 35',           '^IBEX', 'EUR', 60),
            ('continuo','Mercado Continuo',   '^SMSI', 'EUR', 60),
            ('nasdaq',  'Nasdaq',             '^IXIC', 'USD', 365)
    """)

    # 2. Tabla app_config (clave-valor para configuración global)
    op.create_table(
        'app_config',
        sa.Column('key',   sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.execute("INSERT INTO app_config (key, value) VALUES ('snapshot_interval_minutes', '5')")

    # 3. Eliminar CheckConstraint 'ck_securities_market' de securities.
    #    SQLite no soporta DROP CONSTRAINT; Alembic batch_alter_table recrea la tabla.
    with op.batch_alter_table('securities', schema=None) as batch_op:
        batch_op.drop_constraint('ck_securities_market', type_='check')


def downgrade() -> None:
    # Restaurar CheckConstraint en securities
    with op.batch_alter_table('securities', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_securities_market',
            "market IN ('ibex35','continuo','nasdaq')",
        )
    op.drop_table('app_config')
    op.drop_table('markets')
