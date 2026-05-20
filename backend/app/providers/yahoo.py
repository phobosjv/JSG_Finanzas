"""
providers/yahoo.py
==================
Implementacion de PriceProvider usando yfinance.

Decisiones de implementacion
-----------------------------
- Se usa Ticker.history() en lugar de yf.download() porque devuelve un
  DataFrame de columna simple (sin MultiIndex) para un unico ticker, lo
  que simplifica el parseo.
- auto_adjust=True: precios ajustados por splits y dividendos, coherente
  con el precio de mercado que ve el usuario.
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
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf

from app.providers.base import LiveQuote, PriceBar, PriceProvider


def _to_decimal(value: float, places: int = 6) -> Decimal:
    return Decimal(str(round(value, places)))


class YahooProvider(PriceProvider):

    def fetch_history(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[PriceBar]:
        t = yf.Ticker(ticker)
        df = t.history(
            start=from_date.isoformat(),
            end=(to_date + timedelta(days=1)).isoformat(),
            auto_adjust=True,
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

    def fetch_live_quote(self, ticker: str) -> LiveQuote:
        t = yf.Ticker(ticker)
        # 5 dias garantiza al menos 2 sesiones aunque caiga un festivo.
        df = t.history(period="5d", auto_adjust=True)
        if len(df) < 2:
            raise ValueError(
                f"No hay suficientes datos de cotizacion para '{ticker}'"
            )
        last_price = _to_decimal(float(df["Close"].iloc[-1]))
        prev_close = _to_decimal(float(df["Close"].iloc[-2]))

        if prev_close == 0:
            daily_change_pct = Decimal("0.00")
        else:
            daily_change_pct = (
                (last_price - prev_close) / prev_close * Decimal("100")
            ).quantize(Decimal("0.01"))

        last_dividend: Decimal | None = None
        divs = t.dividends
        if divs is not None and not divs.empty:
            last_div_val = float(divs.iloc[-1])
            if not math.isnan(last_div_val) and last_div_val > 0:
                last_dividend = _to_decimal(last_div_val)

        return LiveQuote(
            last_price=last_price,
            prev_close=prev_close,
            daily_change_pct=daily_change_pct,
            last_dividend=last_dividend,
        )
