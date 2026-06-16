"""
providers/yahoo.py
==================
Implementacion de PriceProvider usando yfinance.

Decisiones de implementacion
-----------------------------
- Se usa Ticker.history() en lugar de yf.download() porque devuelve un
  DataFrame de columna simple (sin MultiIndex) para un unico ticker, lo
  que simplifica el parseo.
- auto_adjust=False: precios reales de mercado en cada fecha (no ajustados
  retroactivamente por dividendos). Los splits se gestionan aparte (tabla
  security_splits + lógica en _history_series y _normalize_splits).
- El extremo 'end' de history() es EXCLUSIVO en yfinance, por eso se
  suma un dia a to_date.
- El volumen puede llegar como NaN (p.ej. ETFs en ciertos mercados);
  se convierte a None para no romper la restriccion NOT NULL del modelo.
- Los precios se convierten a Decimal via str() para evitar el ruido
  binario del float64 de numpy. Se redondean a 6 decimales (suficiente
  para cualquier cotizacion real).
- Para el live quote se usan los ultimos 5 dias de historia en lugar de
  fast_info, que es menos estable entre versiones de yfinance.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf

from app.providers.base import LiveQuote, PriceBar, PriceProvider


def _to_decimal(value: float, places: int = 6) -> Decimal:
    return Decimal(str(round(value, places)))


_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def _normalize_isin(raw) -> str | None:
    """Valida la forma de un ISIN (12 caracteres, 2 letras de país + 10).

    Yahoo devuelve '-' cuando no lo conoce; cualquier valor que no encaje en
    el patrón ISIN se descarta para no escribir basura en la BD.
    """
    if not raw or not isinstance(raw, str):
        return None
    candidate = raw.strip().upper()
    return candidate if _ISIN_RE.match(candidate) else None


class YahooProvider(PriceProvider):

    def fetch_history(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[PriceBar]:
        t = yf.Ticker(ticker)
        # auto_adjust=False: precios reales de mercado en cada fecha.
        # Con auto_adjust=True, cuando se paga un dividendo yfinance ajusta
        # retroactivamente TODOS los precios de la ventana (incluyendo el más
        # reciente), lo que distorsiona el precio absoluto. Para el gráfico
        # histórico esto provoca una caída artificial el día del dividendo
        # porque las fechas previas (almacenadas antes del ajuste) tienen
        # precios más altos. Los precios reales son suficientemente correctos
        # para el gráfico de evolución de cartera.
        df = t.history(
            start=from_date.isoformat(),
            end=(to_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
        bars: list[PriceBar] = []
        for dt, row in df.iterrows():
            close_val = float(row["Close"])
            if math.isnan(close_val):
                continue
            vol_raw = row.get("Volume")
            volume = (
                None
                if vol_raw is None or math.isnan(float(vol_raw))
                else int(vol_raw)
            )
            bars.append(PriceBar(
                date=dt.date(),
                close=_to_decimal(close_val),
                volume=volume,
            ))
        return bars

    def fetch_live_quotes(self, tickers: list[str]) -> dict[str, LiveQuote]:
        """
        Cotizaciones en vivo de VARIOS tickers en una sola petición (yf.download),
        para minimizar las llamadas a Yahoo (rate-limit). No incluye dividendos
        (el path en vivo no los necesita). Los tickers que fallen no aparecen en
        el dict devuelto.
        """
        if not tickers:
            return {}
        import pandas as pd

        out: dict[str, LiveQuote] = {}
        try:
            data = yf.download(
                tickers=" ".join(tickers),
                period="5d",
                auto_adjust=False,
                group_by="ticker",
                progress=False,
                threads=False,
            )
        except Exception:
            return out
        if data is None or len(data) == 0:
            return out

        multi = isinstance(data.columns, pd.MultiIndex)
        for tk in tickers:
            try:
                sub = data[tk] if multi else data
                closes = sub["Close"].dropna()
                if len(closes) < 1:
                    continue
                last = float(closes.iloc[-1])
                if math.isnan(last):
                    continue
                last_d = _to_decimal(last)
                # Valor iliquido con un solo cierre: sin dia anterior,
                # prev_close y pct quedan en None (ver fetch_live_quote).
                prev_d: Decimal | None = None
                if len(closes) >= 2:
                    prev = float(closes.iloc[-2])
                    if not math.isnan(prev):
                        prev_d = _to_decimal(prev)

                quote_time: str | None = None
                try:
                    idx = closes.index[-1]
                    if hasattr(idx, "tz_convert"):
                        try:
                            idx = idx.tz_convert("UTC")
                        except (TypeError, ValueError):
                            pass
                    quote_time = idx.isoformat()
                except Exception:
                    pass

                pct: Decimal | None
                if prev_d is None or prev_d == 0:
                    pct = None if prev_d is None else Decimal("0.00")
                else:
                    pct = ((last_d - prev_d) / prev_d * Decimal("100")).quantize(Decimal("0.01"))

                out[tk] = LiveQuote(
                    last_price=last_d, prev_close=prev_d,
                    daily_change_pct=pct, last_dividend=None, quote_time=quote_time,
                )
            except Exception:
                continue
        return out

    def fetch_live_quote(self, ticker: str, with_dividends: bool = True) -> LiveQuote:
        """
        Cotización en vivo. 'with_dividends=False' omite la consulta de
        dividendos (t.dividends), que es una petición ADICIONAL a Yahoo: el job
        en vivo (cada pocos min) no la necesita y así reduce a la mitad las
        peticiones. El dividendo se captura en el barrido nocturno
        (with_dividends=True).
        """
        t = yf.Ticker(ticker)
        # auto_adjust=False para obtener el precio REAL de mercado.
        # auto_adjust=True ajustaría retroactivamente los precios por dividendos
        # y splits, lo que distorsiona el precio absoluto mostrado al usuario
        # (ej: si SAB.MC acaba de pagar un dividendo de 0,50 €, todos los
        # cierres de la ventana de 5 días aparecerían ~14 % más bajos).
        # El porcentaje diario se calcula como ratio y no se ve afectado por
        # el ajuste, pero el precio absoluto sí: se mostraría 2,94 en lugar
        # de 3,44. fetch_history también usa auto_adjust=False; los splits se
        # aplican de forma progresiva en _history_series (sin retroactividad).
        df = t.history(period="5d", auto_adjust=False)
        # Descartar filas con Close NaN (pre-mercado, festivos sin datos)
        df = df.dropna(subset=["Close"])
        if len(df) < 1:
            raise ValueError(
                f"No hay datos de cotizacion para '{ticker}'"
            )
        last_price = _to_decimal(float(df["Close"].iloc[-1]))
        # Valores muy iliquidos (p. ej. NXTE.XD): Yahoo puede publicar un unico
        # cierre. Sin dia anterior no hay variacion → se degrada con prev_close
        # y daily_change_pct a None en lugar de descartar el snapshot por
        # completo, para que el precio y los rangos Min./Max. si se muestren.
        prev_close: Decimal | None = (
            _to_decimal(float(df["Close"].iloc[-2])) if len(df) >= 2 else None
        )

        # Timestamp del último trade según Yahoo (índice del DataFrame).
        # Para mercados intradia: contiene hora exacta del último tick.
        # Para EOD: contiene la fecha del cierre (00:00 UTC).
        quote_time: str | None = None
        try:
            last_idx = df.index[-1]
            # Pandas Timestamp -> ISO 8601 UTC
            if hasattr(last_idx, "tz_convert"):
                try:
                    last_idx = last_idx.tz_convert("UTC")
                except (TypeError, ValueError):
                    pass
            quote_time = last_idx.isoformat()
        except Exception:
            pass

        daily_change_pct: Decimal | None
        if prev_close is None or prev_close == 0:
            daily_change_pct = None if prev_close is None else Decimal("0.00")
        else:
            daily_change_pct = (
                (last_price - prev_close) / prev_close * Decimal("100")
            ).quantize(Decimal("0.01"))

        last_dividend: Decimal | None = None
        divs = t.dividends
        if divs is not None and not divs.empty:
            raw = divs.iloc[-1]
            # yfinance puede devolver Series (DataFrame multi-col) o escalar
            last_div_val = float(raw.iloc[0] if hasattr(raw, 'iloc') else raw)
            if not math.isnan(last_div_val) and last_div_val > 0:
                last_dividend = _to_decimal(last_div_val)

        return LiveQuote(
            last_price=last_price,
            prev_close=prev_close,
            daily_change_pct=daily_change_pct,
            last_dividend=last_dividend,
            quote_time=quote_time,
        )

    def fetch_isin(self, ticker: str) -> str | None:
        """
        ISIN del valor según Yahoo (`Ticker.isin`). Devuelve None si Yahoo no
        lo conoce (devuelve '-' o cadena vacía) o si la respuesta no tiene
        forma de ISIN válido. No lanza: cualquier fallo de red se traduce en
        None para que el pipeline pueda continuar con el resto de valores.
        """
        try:
            raw = yf.Ticker(ticker).isin
        except Exception:
            return None
        return _normalize_isin(raw)
