"""v1.3.0 — user subscriptions: is_enabled, expires_at, user_status_log, app_name

Revision ID: c7f9e2b4d8a1
Revises: a3f9c1d2e5b4
Create Date: 2026-05-23

Cambios:
  - Añade is_enabled (bool, default 1) y expires_at (datetime nullable) a users.
  - Crea tabla user_status_log para historial de estados por usuario.
  - Inserta clave app_name en app_config con valor por defecto 'FJS Finanzas'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7f9e2b4d8a1'
down_revision: Union[str, None] = 'a3f9c1d2e5b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Nuevas columnas en users (batch para SQLite)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(), nullable=True))

    # 2. Tabla user_status_log
    op.create_table(
        'user_status_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('annotation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_user_status_log_user_id', 'user_status_log', ['user_id'])

    # 3. Insertar app_name en app_config
    op.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('app_name', 'FJS Finanzas')")


def downgrade() -> None:
    op.execute("DELETE FROM app_config WHERE key = 'app_name'")
    op.drop_index('ix_user_status_log_user_id', 'user_status_log')
    op.drop_table('user_status_log')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('expires_at')
        batch_op.drop_column('is_enabled')
