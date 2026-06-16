"""
api/admin_markets.py
====================
Gestión del catálogo de mercados. Solo administradores.

GET    /admin/markets            — lista todos los mercados.
POST   /admin/markets            — crea un mercado nuevo.
PATCH  /admin/markets/{code}     — actualiza un mercado existente.
DELETE /admin/markets/{code}     — elimina un mercado (solo si no tiene valores).

GET    /admin/config             — devuelve la configuración global (incluye intervalo).
PATCH  /admin/config/snapshot-interval — cambia el intervalo de actualización de snapshots.
"""

from __future__ import annotations

import base64
import json
import logging
import threading as _threading
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models import AppConfig, MarketRow, Security, TaxBracketRow, User
from app.providers.ecb import ECB_CURRENCIES
from app.schemas.market_admin import (
    AppNameUpdate, CatalogImportBody, CurrenciesUpdate, DustThresholdUpdate, EmailConfigIn,
    EmailConfigOut, LogoUpdate, MarketCreate, MarketOut, MarketReorderItem, MarketUpdate,
    SnapshotIntervalUpdate,
)
from app.repositories.portfolio_repository import DUST_THRESHOLD_KEY, get_dust_threshold
from app.schemas.tax_bracket import TaxBracketCreate, TaxBracketOut
from app.services.email_notifications import EMAIL_CONFIG_KEY, load_email_config
from app.services.email_service import EmailConfig, send_email

router = APIRouter(prefix="/admin", tags=["admin"])
log = logging.getLogger(__name__)

_CONFIG_INTERVAL_KEY      = "snapshot_interval_minutes"
_CONFIG_APP_NAME_KEY      = "app_name"
_CONFIG_LOGO_DATA_KEY     = "logo_data"
_CONFIG_LOGO_MIME_KEY     = "logo_mime"
_CONFIG_LOGO_UPDATED_KEY  = "logo_updated_at"
_CONFIG_CURRENCIES_KEY    = "supported_currencies"
_APP_NAME_DEFAULT         = "JSG Soft."
_CURRENCIES_DEFAULT       = "USD"  # EUR siempre implícita; esta clave guarda las demás


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _require_market(db: Session, code: str) -> MarketRow:
    m = db.get(MarketRow, code)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Mercado '{code}' no encontrado")
    return m


def _get_interval(db: Session) -> int:
    row = db.get(AppConfig, _CONFIG_INTERVAL_KEY)
    return int(row.value) if row else 5


def _get_app_name(db: Session) -> str:
    row = db.get(AppConfig, _CONFIG_APP_NAME_KEY)
    return row.value if row else _APP_NAME_DEFAULT


def _get_supported_currencies(db: Session) -> list[str]:
    """EUR es la divisa base (siempre válida). La clave guarda las adicionales."""
    row = db.get(AppConfig, _CONFIG_CURRENCIES_KEY)
    raw = row.value if row else _CURRENCIES_DEFAULT
    extras = [c.strip().upper() for c in raw.split(",")
              if c.strip() and c.strip().upper() != "EUR"]
    return ["EUR"] + extras


def _require_supported_currency(db: Session, currency: str) -> None:
    """422 si la divisa no está entre las soportadas (multi-divisa v1.8.0)."""
    if currency.strip().upper() not in _get_supported_currencies(db):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"La divisa '{currency}' no está soportada (configúrala en Admin)",
        )


# ---------------------------------------------------------------------------
#  Mercados
# ---------------------------------------------------------------------------

@router.get("/markets", response_model=list[MarketOut])
def list_markets(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return db.scalars(select(MarketRow).order_by(MarketRow.sort_order, MarketRow.code)).all()


@router.post("/markets", response_model=MarketOut, status_code=status.HTTP_201_CREATED)
def create_market(
    body: MarketCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.get(MarketRow, body.code):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"El código de mercado '{body.code}' ya existe")
    _require_supported_currency(db, body.currency)
    # market_type manda; is_fund_market se deriva. Compat: un cliente antiguo que
    # solo manda is_fund_market=True (sin tipo) se interpreta como 'fund'.
    market_type = body.market_type
    if market_type == "stock" and body.is_fund_market:
        market_type = "fund"
    market = MarketRow(
        code=body.code,
        name=body.name,
        index_ticker=body.index_ticker,
        currency=body.currency,
        fiscal_window_days=body.fiscal_window_days,
        sort_order=body.sort_order,
        yahoo_exchange=body.yahoo_exchange.strip().upper() if body.yahoo_exchange else None,
        market_type=market_type,
        is_fund_market=(market_type == "fund"),
        created_at=datetime.now().isoformat(),
    )
    db.add(market)
    db.commit()
    db.refresh(market)
    return market


@router.patch("/markets/{code}", response_model=MarketOut)
def update_market(
    code: str,
    body: MarketUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    market = _require_market(db, code)
    if body.name is not None:
        market.name = body.name
    if body.index_ticker is not None:
        market.index_ticker = body.index_ticker
    if body.currency is not None:
        _require_supported_currency(db, body.currency)
        market.currency = body.currency.strip().upper()
    if body.fiscal_window_days is not None:
        market.fiscal_window_days = body.fiscal_window_days
    if body.sort_order is not None:
        market.sort_order = body.sort_order
    if body.yahoo_exchange is not None:
        # Guardar None si se envía string vacío (para "borrar" el exchange)
        market.yahoo_exchange = body.yahoo_exchange.strip().upper() or None
    # El tipo manda y deriva is_fund_market. Si solo llega is_fund_market (cliente
    # antiguo), se ajusta el tipo en consecuencia.
    if body.market_type is not None:
        market.market_type = body.market_type
        market.is_fund_market = (body.market_type == "fund")
    elif body.is_fund_market is not None:
        market.is_fund_market = body.is_fund_market
        if body.is_fund_market:
            market.market_type = "fund"
        elif market.market_type == "fund":
            market.market_type = "stock"
    db.commit()
    db.refresh(market)
    return market


@router.post("/markets/{code}/sync-currency")
def sync_market_currency(
    code: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Fija la divisa de TODOS los valores del mercado a la divisa del mercado
    "padre". Útil para corregir valores dados de alta con la divisa equivocada
    (p. ej. acciones extranjeras creadas en EUR). Devuelve cuántos se cambiaron.
    """
    market = _require_market(db, code)
    secs = db.scalars(select(Security).where(Security.market == code)).all()
    updated = 0
    for s in secs:
        if s.currency != market.currency:
            s.currency = market.currency
            updated += 1
    db.commit()
    return {"updated": updated, "total": len(secs), "currency": market.currency}


@router.delete("/markets/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_market(
    code: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    market = _require_market(db, code)
    # Impedir borrado si hay valores asignados a este mercado
    count = db.scalar(
        select(func.count(Security.id)).where(Security.market == code)
    )
    if count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El mercado '{code}' tiene valores asignados; reasígnalos antes de eliminarlo",
        )
    db.delete(market)
    db.commit()


@router.put("/markets/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_markets(
    body: list[MarketReorderItem],
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Actualiza el sort_order de varios mercados en una sola llamada.
    Recibe [{code, sort_order}, ...] y aplica el nuevo orden.
    Los códigos que no existan se ignoran silenciosamente.
    """
    for item in body:
        market = db.get(MarketRow, item.code)
        if market:
            market.sort_order = item.sort_order
    db.commit()


# ---------------------------------------------------------------------------
#  Exportación / importación del catálogo de mercados y valores
# ---------------------------------------------------------------------------

@router.get("/catalog/export")
def export_catalog(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Exporta el catálogo completo de mercados y valores en JSON descargable.
    El fichero resultante puede importarse en otro servidor con POST /catalog/import.
    """
    markets = db.scalars(select(MarketRow).order_by(MarketRow.code)).all()
    securities = db.scalars(select(Security).order_by(Security.name)).all()

    payload = {
        "exported_at": date.today().isoformat(),
        "markets": [
            {
                "code": m.code,
                "name": m.name,
                "index_ticker": m.index_ticker,
                "currency": m.currency,
                "fiscal_window_days": m.fiscal_window_days,
                "sort_order": m.sort_order,
                "market_type": m.market_type,
                "is_fund_market": m.is_fund_market,  # derivado; se mantiene por compat
            }
            for m in markets
        ],
        "securities": [
            {
                "name": s.name,
                "isin": s.isin,
                "yahoo_ticker": s.yahoo_ticker,
                "google_ticker": s.google_ticker,
                "market": s.market,
                "currency": s.currency,
            }
            for s in securities
        ],
    }

    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    today = date.today().isoformat()
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="catalogo_valores_{today}.json"'
        },
    )


@router.post("/catalog/import")
def import_catalog(
    body: CatalogImportBody,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Importa un catálogo de mercados y valores desde JSON.

    Reglas de deduplicación:
    - Mercados: índice = code (PK). Si el código ya existe, se omite.
    - Valores  : índice = yahoo_ticker (UNIQUE global). Si el ticker ya
                 existe en cualquier mercado, se omite (no se mueve de mercado).

    Devuelve los contadores de importados / omitidos para dar feedback al admin.
    """
    markets_imported = 0
    markets_skipped = 0

    # — Paso 1: importar mercados (code = PK) —————————————————————————————
    for m in body.markets:
        code = m.code.strip().lower()
        if not code:
            markets_skipped += 1
            continue
        if db.get(MarketRow, code) is None:
            # market_type: usar el del fichero o derivarlo (compat con exports
            # anteriores a v1.7.6 que no lo traían).
            mt = m.market_type
            if mt is None:
                if m.is_fund_market:
                    mt = "fund"
                elif "etf" in code:
                    mt = "etf"
                elif "crypto" in code:
                    mt = "crypto"
                else:
                    mt = "stock"
            db.add(
                MarketRow(
                    code=code,
                    name=m.name.strip() or code,
                    index_ticker=m.index_ticker or None,
                    currency=(m.currency or "EUR").upper(),
                    fiscal_window_days=max(1, m.fiscal_window_days or 60),
                    sort_order=m.sort_order,
                    market_type=mt,
                    is_fund_market=(mt == "fund"),
                    created_at=datetime.now().isoformat(),
                )
            )
            markets_imported += 1
        else:
            markets_skipped += 1

    # flush para que los mercados recién importados sean visibles en el paso 2
    if markets_imported > 0:
        db.flush()

    # — Paso 2: importar valores (yahoo_ticker = UNIQUE global) ——————————
    existing_tickers: set[str] = set(
        db.scalars(select(Security.yahoo_ticker))
    )

    securities_imported = 0
    securities_skipped = 0
    securities_no_market = 0

    for s in body.securities:
        ticker = s.yahoo_ticker.strip().upper()
        if not ticker:
            securities_skipped += 1
            continue

        # Ya existe en la BD (en cualquier mercado)
        if ticker in existing_tickers:
            securities_skipped += 1
            continue

        # Divisa válida: debe estar entre las soportadas (multi-divisa v1.8.0).
        currency = (s.currency or "EUR").upper()
        if currency not in set(_get_supported_currencies(db)):
            securities_skipped += 1
            continue

        # El mercado debe existir (en la BD original o recién importado)
        market_code = (s.market or "").strip().lower()
        if not market_code or db.get(MarketRow, market_code) is None:
            securities_no_market += 1
            continue

        db.add(
            Security(
                name=s.name.strip(),
                isin=s.isin or None,
                yahoo_ticker=ticker,
                google_ticker=s.google_ticker or None,
                market=market_code,
                currency=currency,
            )
        )
        existing_tickers.add(ticker)  # evitar duplicados dentro del mismo lote
        securities_imported += 1

    db.commit()

    return {
        "markets_imported":      markets_imported,
        "markets_skipped":       markets_skipped,
        "securities_imported":   securities_imported,
        "securities_skipped":    securities_skipped,
        "securities_no_market":  securities_no_market,
    }


# ---------------------------------------------------------------------------
#  Configuración global
# ---------------------------------------------------------------------------

@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    logo_updated = db.get(AppConfig, _CONFIG_LOGO_UPDATED_KEY)
    email_row = db.get(AppConfig, EMAIL_CONFIG_KEY)
    email_provider: str | None = None
    if email_row:
        try:
            email_provider = json.loads(email_row.value).get("provider")
        except Exception:
            pass
    return {
        "snapshot_interval_minutes": _get_interval(db),
        "app_name": _get_app_name(db),
        "has_logo": db.get(AppConfig, _CONFIG_LOGO_DATA_KEY) is not None,
        "logo_updated_at": logo_updated.value if logo_updated else None,
        "supported_currencies": _get_supported_currencies(db),
        "dust_threshold": str(get_dust_threshold(db)),
        "email_configured": email_row is not None,
        "email_provider": email_provider,
    }


@router.get("/config/email", response_model=EmailConfigOut)
def get_email_config(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Devuelve la configuración de email con contraseña/api_key enmascaradas."""
    config = load_email_config(db)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay configuración de email guardada",
        )
    return EmailConfigOut(
        provider=config.provider,
        from_name=config.from_name,
        from_address=config.from_address,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_password="***" if config.smtp_password else None,
        smtp_use_tls=config.smtp_use_tls,
        api_key="***" if config.api_key else None,
        mailgun_domain=config.mailgun_domain,
    )


@router.patch("/config/email", response_model=EmailConfigOut)
def set_email_config(
    body: EmailConfigIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Guarda la configuración de email. Si smtp_password o api_key vienen como
    '***', se conserva el valor existente en BD (no se sobreescribe)."""
    existing = load_email_config(db)

    # Resolver contraseña y api_key: si "***" llega, conservar la actual
    password = body.smtp_password
    if password == "***":
        password = existing.smtp_password if existing else None

    api_key = body.api_key
    if api_key == "***":
        api_key = existing.api_key if existing else None

    config = EmailConfig(
        provider=body.provider,
        from_name=body.from_name,
        from_address=body.from_address,
        smtp_host=body.smtp_host,
        smtp_port=body.smtp_port,
        smtp_user=body.smtp_user,
        smtp_password=password,
        smtp_use_tls=body.smtp_use_tls,
        api_key=api_key,
        mailgun_domain=body.mailgun_domain,
    )
    _upsert_config(db, EMAIL_CONFIG_KEY, json.dumps(config.__dict__))
    db.commit()
    return EmailConfigOut(
        provider=config.provider,
        from_name=config.from_name,
        from_address=config.from_address,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_password="***" if config.smtp_password else None,
        smtp_use_tls=config.smtp_use_tls,
        api_key="***" if config.api_key else None,
        mailgun_domain=config.mailgun_domain,
    )


@router.post("/config/email/test")
def test_email_config(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Envía un email de prueba al email del administrador logueado.

    422 si el admin no tiene email configurado o si la configuración de email
    no existe. 422 con detalle si el envío falla.
    """
    if not admin.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Configura primero tu email en la tabla de usuarios",
        )
    config = load_email_config(db)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No hay configuración de email guardada",
        )
    try:
        body_html = (
            "<h2>Correo de prueba</h2>"
            "<p>Si recibes este mensaje, la configuración de email funciona correctamente.</p>"
            "<p><small>JSG Portfolio — configuración de notificaciones</small></p>"
        )
        send_email(config, admin.email, "Prueba de configuración de email", body_html)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error al enviar el email: {exc}",
        )
    return {"sent_to": admin.email}


@router.patch("/config/dust-threshold")
def set_dust_threshold(
    body: DustThresholdUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Fija el umbral de 'polvo' (coste de lotes vivos por debajo del cual una
    posición se considera cerrada). En divisa nativa."""
    value = str(body.dust_threshold)
    row = db.get(AppConfig, DUST_THRESHOLD_KEY)
    if row is None:
        db.add(AppConfig(key=DUST_THRESHOLD_KEY, value=value))
    else:
        row.value = value
    db.commit()
    return {"dust_threshold": value}


@router.patch("/config/app-name")
def set_app_name(
    body: AppNameUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = db.get(AppConfig, _CONFIG_APP_NAME_KEY)
    if row is None:
        db.add(AppConfig(key=_CONFIG_APP_NAME_KEY, value=body.app_name))
    else:
        row.value = body.app_name
    db.commit()
    return {"app_name": body.app_name}


@router.get("/config/available-currencies")
def available_currencies(_admin: User = Depends(require_admin)):
    """Divisas que el BCE publica (las únicas que la app puede manejar). Alimenta
    el buscador del AdminPanel y es la lista contra la que se valida el alta."""
    return {"available_currencies": list(ECB_CURRENCIES)}


def _backfill_currency_rates() -> None:
    """Descarga los tipos del BCE (todas las divisas, idempotente) en un hilo,
    para que una divisa recién añadida quede operativa al instante incluso si la
    BD solo tenía USD. Reutiliza el job nocturno; los huecos se rellenan solos."""
    def _run() -> None:
        from app.database import SessionLocal
        from app.scheduler.jobs import update_ecb_rates
        db = SessionLocal()
        try:
            update_ecb_rates(db)
        except Exception:
            log.exception("Error en backfill de tipos BCE tras añadir divisa")
        finally:
            db.close()

    _threading.Thread(target=_run, daemon=True, name="currency-backfill").start()


@router.patch("/config/currencies")
def set_currencies(
    body: CurrenciesUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Actualiza la lista de divisas soportadas. EUR siempre es válida (no se almacena).
    Solo se aceptan divisas que el BCE publica (ECB_CURRENCIES); cualquier otra se
    rechaza con 422. Al añadir divisas nuevas se dispara el backfill de tipos BCE."""
    previous = set(_get_supported_currencies(db)) - {"EUR"}
    codes: list[str] = []
    for code in body.currencies:
        c = code.strip().upper()
        if len(c) != 3 or not c.isalpha():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Código de divisa inválido: '{code}' (debe ser 3 letras)"
            )
        if c == "EUR":
            continue
        if c not in ECB_CURRENCIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"El BCE no publica la divisa '{c}'; no puede usarse en la app"
            )
        if c not in codes:
            codes.append(c)
    value = ",".join(codes) if codes else ""
    _upsert_config(db, _CONFIG_CURRENCIES_KEY, value)
    db.commit()

    # Backfill solo si hay divisas nuevas respecto a las ya soportadas.
    if set(codes) - previous:
        _backfill_currency_rates()

    return {"supported_currencies": ["EUR"] + codes}


def _upsert_config(db: Session, key: str, value: str) -> None:
    row = db.get(AppConfig, key)
    if row is None:
        db.add(AppConfig(key=key, value=value))
    else:
        row.value = value


@router.put("/config/logo")
def set_logo(
    body: LogoUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Guarda el logotipo de la app (base64) tras validar tipo y tamaño."""
    try:
        blob, mime = body.decoded()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )

    # Re-codificar canónicamente para no almacenar el prefijo data-URI.
    updated_at = datetime.now().isoformat(timespec="seconds")
    _upsert_config(db, _CONFIG_LOGO_DATA_KEY, base64.b64encode(blob).decode("ascii"))
    _upsert_config(db, _CONFIG_LOGO_MIME_KEY, mime)
    _upsert_config(db, _CONFIG_LOGO_UPDATED_KEY, updated_at)
    db.commit()
    return {"has_logo": True, "logo_updated_at": updated_at}


@router.delete("/config/logo", status_code=status.HTTP_204_NO_CONTENT)
def delete_logo(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Elimina el logotipo personalizado y vuelve a los iconos por defecto."""
    for key in (_CONFIG_LOGO_DATA_KEY, _CONFIG_LOGO_MIME_KEY, _CONFIG_LOGO_UPDATED_KEY):
        row = db.get(AppConfig, key)
        if row is not None:
            db.delete(row)
    db.commit()


@router.patch("/config/snapshot-interval")
def set_snapshot_interval(
    body: SnapshotIntervalUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = db.get(AppConfig, _CONFIG_INTERVAL_KEY)
    if row is None:
        db.add(AppConfig(key=_CONFIG_INTERVAL_KEY, value=str(body.minutes)))
    else:
        row.value = str(body.minutes)
    db.commit()

    # Reprogramar el job en APScheduler sin reiniciar el servidor
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        try:
            scheduler.reschedule_job(
                "snapshot_live",
                trigger="interval",
                minutes=body.minutes,
            )
        except Exception:
            pass  # El job no existe aún o el scheduler está parado; no es crítico

    return {"snapshot_interval_minutes": body.minutes}


# ---------------------------------------------------------------------------
#  Tramos IRPF
# ---------------------------------------------------------------------------

def _require_bracket(db: Session, bracket_id: int) -> TaxBracketRow:
    b = db.get(TaxBracketRow, bracket_id)
    if b is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Tramo id={bracket_id} no encontrado")
    return b


@router.get("/config/tax-brackets", response_model=list[TaxBracketOut])
def list_tax_brackets(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return db.scalars(
        select(TaxBracketRow).order_by(TaxBracketRow.sort_order, TaxBracketRow.id)
    ).all()


@router.post("/config/tax-brackets", response_model=TaxBracketOut,
             status_code=status.HTTP_201_CREATED)
def create_tax_bracket(
    body: TaxBracketCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    bracket = TaxBracketRow(
        min_amount=body.min_amount,
        max_amount=body.max_amount,
        rate=body.rate,
        sort_order=body.sort_order,
    )
    db.add(bracket)
    db.commit()
    db.refresh(bracket)
    return bracket


@router.put("/config/tax-brackets/{bracket_id}", response_model=TaxBracketOut)
def update_tax_bracket(
    bracket_id: int,
    body: TaxBracketCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    bracket = _require_bracket(db, bracket_id)
    bracket.min_amount = body.min_amount
    bracket.max_amount = body.max_amount
    bracket.rate = body.rate
    bracket.sort_order = body.sort_order
    db.commit()
    db.refresh(bracket)
    return bracket


@router.delete("/config/tax-brackets/{bracket_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_tax_bracket(
    bracket_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    bracket = _require_bracket(db, bracket_id)
    db.delete(bracket)
    db.commit()


# ---------------------------------------------------------------------------
#  Explorador de valores Yahoo Finance
# ---------------------------------------------------------------------------

@router.get("/securities/search")
def search_yahoo_securities(
    q: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Busca valores en Yahoo Finance por nombre o ticker y comprueba si ya
    están en el catálogo local. Devuelve hasta 15 resultados.

    Respuesta por ítem:
      ticker, name, exchange, type, currency,
      in_catalog (bool), catalog_market (str|None)
    """
    if not q or not q.strip():
        return []

    import yfinance as yf

    try:
        search = yf.Search(q.strip(), max_results=15, enable_fuzzy_query=True)
        quotes = search.quotes or []
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Yahoo Finance no disponible: {exc}",
        )

    if not quotes:
        return []

    # Pre-cargar los tickers que ya están en catálogo en una sola consulta
    tickers_in_query = [q_item.get("symbol", "").upper() for q_item in quotes if q_item.get("symbol")]
    existing: dict[str, str] = {}
    if tickers_in_query:
        rows = db.scalars(
            select(Security).where(Security.yahoo_ticker.in_(tickers_in_query))
        ).all()
        existing = {sec.yahoo_ticker.upper(): sec.market for sec in rows}

    results = []
    for item in quotes:
        symbol = (item.get("symbol") or "").upper()
        if not symbol:
            continue
        name = item.get("shortname") or item.get("longname") or symbol
        results.append({
            "ticker":        symbol,
            "name":          name,
            "exchange":      item.get("exchDisp") or item.get("exchange") or "",
            "type":          item.get("quoteType") or "",
            "currency":      (item.get("currency") or "").upper() or None,
            "in_catalog":    symbol in existing,
            "catalog_market": existing.get(symbol),
        })

    return results


# ---------------------------------------------------------------------------
#  Explorador Yahoo Finance filtrado por mercado
# ---------------------------------------------------------------------------

@router.get("/markets/{code}/yahoo-securities")
def search_yahoo_by_market(
    code: str,
    q: str = "",
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Busca valores en Yahoo Finance filtrando por el exchange del mercado dado.

    Requiere que el mercado tenga `yahoo_exchange` configurado (ej. "MCE").
    Devuelve los resultados de yf.Search que pertenecen a ese exchange,
    marcando cuáles están ya en el catálogo.
    """
    market = _require_market(db, code)

    if not market.yahoo_exchange:
        return {"error": "no_exchange_configured", "results": []}

    if not q or not q.strip():
        return {"error": None, "results": []}

    import yfinance as yf

    exchange = market.yahoo_exchange.upper()

    try:
        search = yf.Search(q.strip(), max_results=50, enable_fuzzy_query=True)
        quotes = search.quotes or []
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Yahoo Finance no disponible: {exc}",
        )

    # Filtrar solo los que pertenecen al exchange del mercado
    filtered = [
        item for item in quotes
        if (item.get("exchange") or "").upper() == exchange
    ]

    if not filtered:
        return {"error": None, "results": []}

    # Comprobar cuáles están ya en el catálogo
    tickers = [item.get("symbol", "").upper() for item in filtered if item.get("symbol")]
    existing: dict[str, str] = {}
    if tickers:
        rows = db.scalars(
            select(Security).where(Security.yahoo_ticker.in_(tickers))
        ).all()
        existing = {sec.yahoo_ticker.upper(): sec.market for sec in rows}

    results = []
    for item in filtered:
        symbol = (item.get("symbol") or "").upper()
        if not symbol:
            continue
        name = item.get("shortname") or item.get("longname") or symbol
        results.append({
            "ticker":         symbol,
            "name":           name,
            "exchange":       item.get("exchDisp") or item.get("exchange") or "",
            "type":           item.get("quoteType") or "",
            "currency":       (item.get("currency") or "").upper() or None,
            "in_catalog":     symbol in existing,
            "catalog_market": existing.get(symbol),
        })

    return {"error": None, "results": results}


# Tope de seguridad: nº máximo de valores a traer de un exchange (evita
# exchanges enormes que tardarían demasiado o agotarían rate-limit de Yahoo).
_SCREEN_PAGE_SIZE = 250
_SCREEN_MAX_TOTAL = 2000


@router.get("/markets/{code}/yahoo-list-all")
def list_all_yahoo_by_market(
    code: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Lista TODOS los valores (acciones) del exchange Yahoo del mercado dado.

    Usa el screener de Yahoo (yf.screen + EquityQuery) paginando de 250 en 250
    hasta agotar resultados o alcanzar el tope de seguridad. Marca cuáles ya
    están en el catálogo.

    Limitación: EquityQuery lista acciones (EQUITY). ETFs y cripto usan otro
    tipo de query y pueden no aparecer; para esos mercados, usar la búsqueda
    por texto.
    """
    market = _require_market(db, code)

    if not market.yahoo_exchange:
        return {"error": "no_exchange_configured", "results": [], "total": 0}

    import yfinance as yf

    exchange = market.yahoo_exchange.upper()

    try:
        query = yf.EquityQuery("eq", ["exchange", exchange])
        all_quotes: list[dict] = []
        total_reported = 0
        offset = 0
        while offset < _SCREEN_MAX_TOTAL:
            res = yf.screen(query, offset=offset, size=_SCREEN_PAGE_SIZE)
            if not isinstance(res, dict):
                break
            total_reported = res.get("total", total_reported)
            page = res.get("quotes", []) or []
            if not page:
                break
            all_quotes.extend(page)
            if len(page) < _SCREEN_PAGE_SIZE:
                break
            offset += _SCREEN_PAGE_SIZE
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Yahoo Finance no disponible: {exc}",
        )

    if not all_quotes:
        return {"error": None, "results": [], "total": 0}

    # Comprobar cuáles ya están en el catálogo (una sola consulta)
    tickers = [item.get("symbol", "").upper() for item in all_quotes if item.get("symbol")]
    existing: dict[str, str] = {}
    if tickers:
        rows = db.scalars(
            select(Security).where(Security.yahoo_ticker.in_(tickers))
        ).all()
        existing = {sec.yahoo_ticker.upper(): sec.market for sec in rows}

    results = []
    seen: set[str] = set()
    for item in all_quotes:
        symbol = (item.get("symbol") or "").upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        name = item.get("shortName") or item.get("longName") or symbol
        results.append({
            "ticker":         symbol,
            "name":           name,
            "exchange":       item.get("exchDisp") or item.get("exchange") or exchange,
            "type":           item.get("quoteType") or "",
            "currency":       (item.get("currency") or "").upper() or None,
            "in_catalog":     symbol in existing,
            "catalog_market": existing.get(symbol),
        })

    # Ordenar: primero los que faltan por añadir, luego por ticker
    results.sort(key=lambda r: (r["in_catalog"], r["ticker"]))

    return {"error": None, "results": results, "total": total_reported or len(results)}
