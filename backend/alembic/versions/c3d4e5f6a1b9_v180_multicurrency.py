"""v1.8.0 - multi-divisa: ecb_rates (date,currency) + quitar CHECK currency

Revision ID: c3d4e5f6a1b9
Revises: b2c3d4e5f7a8
Create Date: 2026-06-03

- ecb_rates pasa de PK (date) a PK (date, currency): el BCE publica ~30 divisas
  y se cachean por divisa. Los datos existentes se conservan como 'USD'.
- Se elimina el CHECK 'currency IN (EUR,USD)' de securities: las divisas son
  ahora dinámicas (validadas en la API contra las divisas soportadas).
"""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a1b9"
down_revision = "b2c3d4e5f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- ecb_rates → PK (date, currency), preservando existentes como USD ---
    op.execute("ALTER TABLE ecb_rates RENAME TO ecb_rates_old")
    op.execute(
        """
        CREATE TABLE ecb_rates (
            date     TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            rate     REAL NOT NULL,
            PRIMARY KEY (date, currency)
        )
        """
    )
    op.execute(
        "INSERT INTO ecb_rates (date, currency, rate) "
        "SELECT date, 'USD', rate FROM ecb_rates_old"
    )
    op.execute("DROP TABLE ecb_rates_old")

    # --- securities: quitar el CHECK de currency (multi-divisa) ---
    with op.batch_alter_table("securities") as batch_op:
        batch_op.drop_constraint("ck_securities_currency", type_="check")


def downgrade() -> None:
    with op.batch_alter_table("securities") as batch_op:
        batch_op.create_check_constraint(
            "ck_securities_currency", "currency IN ('EUR','USD')"
        )

    op.execute("ALTER TABLE ecb_rates RENAME TO ecb_rates_old")
    op.execute(
        "CREATE TABLE ecb_rates (date TEXT NOT NULL PRIMARY KEY, rate REAL NOT NULL)"
    )
    op.execute(
        "INSERT OR IGNORE INTO ecb_rates (date, rate) "
        "SELECT date, rate FROM ecb_rates_old WHERE currency = 'USD'"
    )
    op.execute("DROP TABLE ecb_rates_old")
