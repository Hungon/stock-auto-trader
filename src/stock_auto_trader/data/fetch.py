from __future__ import annotations

from datetime import date, datetime, time, timezone

import pandas as pd

from stock_auto_trader.broker.alpaca import AlpacaBroker
from stock_auto_trader.config import Settings
from stock_auto_trader.data import yfinance_provider
from stock_auto_trader.markets.aliases import map_symbol_for_market
from stock_auto_trader.markets.detect import is_japan_symbol, normalize_symbol


def resolve_ticker(
    symbol: str,
    settings: Settings,
    *,
    market_hint: str | None = None,
) -> tuple[str, str, str | None]:
    """Return (ticker, market, alias_note)."""
    # Tokyo tickers (.T or 4-digit code) always use Yahoo Japan — never Alpaca.
    if is_japan_symbol(symbol):
        return normalize_symbol(symbol, "jp"), "jp", None

    hint = (market_hint or settings.market or "auto").strip().lower()
    if hint == "auto":
        if is_japan_symbol(symbol):
            return normalize_symbol(symbol, "jp"), "jp", None
        return symbol.strip().upper(), "us", None
    mapped, note = map_symbol_for_market(symbol, hint)
    if hint == "jp":
        return normalize_symbol(mapped, "jp"), "jp", note
    return normalize_symbol(mapped, "us"), "us", note


def fetch_bars_between(
    settings: Settings,
    symbol: str,
    start: date,
    end: date,
    *,
    broker: AlpacaBroker | None = None,
    market_hint: str | None = None,
) -> pd.DataFrame:
    ticker, market, _ = resolve_ticker(symbol, settings, market_hint=market_hint)
    if market == "jp":
        return yfinance_provider.fetch_bars_between(ticker, start, end, settings)

    if broker is None:
        broker = AlpacaBroker(settings)
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max.replace(microsecond=0), tzinfo=timezone.utc)
    return broker.fetch_bars_between(ticker, start_dt, end_dt)


def fetch_latest_tick(
    settings: Settings,
    symbol: str,
    *,
    broker: AlpacaBroker | None = None,
    market_hint: str | None = None,
) -> dict:
    ticker, market, _ = resolve_ticker(symbol, settings, market_hint=market_hint)
    if market == "jp":
        return yfinance_provider.fetch_latest_tick(ticker, settings)

    if broker is None:
        broker = AlpacaBroker(settings)
    tick = broker.fetch_latest_tick(ticker)
    tick["market"] = "us"
    return tick
