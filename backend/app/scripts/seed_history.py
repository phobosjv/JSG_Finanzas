"""
scripts/seed_history.py
=======================
Carga inicial de 5 años de histórico de cotizaciones y tipos BCE
para todos los valores del catálogo.

Uso:
    cd backend
    python -m app.scripts.seed_history

El script es idempotente: usa ON CONFLICT DO NOTHING, por lo que se
puede relanzar sin riesgo si se interrumpe a mitad.
"""

import logging
import sys
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Security
    from app.scheduler.jobs import (
        _update_history_for_security,
        update_ecb_rates,
    )

    db = SessionLocal()
    try:
        securities = db.scalars(select(Security)).all()
        if not securities:
            log.warning("No hay valores en el catálogo. Añade valores primero en Utilidades.")
            sys.exit(0)

        today = date.today()
        log.info("Descargando histórico de %d valores…", len(securities))
        for sec in securities:
            log.info("  %s", sec.yahoo_ticker)
            try:
                _update_history_for_security(db, sec, today)
            except Exception:
                log.exception("  Error en %s (se continúa con el siguiente)", sec.yahoo_ticker)

        log.info("Descargando tipos BCE (5 años)…")
        update_ecb_rates(db)

        log.info("Seed completado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
