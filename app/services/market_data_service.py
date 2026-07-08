"""Market data + currency service.

Thin orchestration layer over the broker, data providers, currency helpers, and
demo/synthetic data used by the market API router.
"""

from __future__ import annotations

from app.broker.alpaca import AlpacaBroker
from app.chart.currency_apply import (
    apply_currency_to_chart_payload,
    apply_currency_to_tick,
)
from app.chart.demo import demo_settings, generate_demo_bars
from app.chart.live import demo_tick
from app.chart.series import build_chart_payload
from app.core.config import Settings
from app.currency import (
    build_conversion_info,
    convert_amount,
    get_usdjpy_rate,
    native_currency_for_symbol,
    resolve_display_currency,
)
from app.data.fetch import fetch_bars_between, fetch_latest_tick, resolve_ticker
from app.markets.symbols import JAPAN_STOCKS, US_STOCKS

__all__ = [
    "AlpacaBroker",
    "apply_currency_to_chart_payload",
    "apply_currency_to_tick",
    "demo_settings",
    "generate_demo_bars",
    "demo_tick",
    "build_chart_payload",
    "build_conversion_info",
    "convert_amount",
    "get_usdjpy_rate",
    "native_currency_for_symbol",
    "resolve_display_currency",
    "fetch_bars_between",
    "fetch_latest_tick",
    "resolve_ticker",
    "JAPAN_STOCKS",
    "US_STOCKS",
    "currency_bundle",
]


def currency_bundle(
    settings: Settings,
    symbol: str,
    currency: str | None,
    market_hint: str | None = None,
) -> tuple[str, str, float, bool]:
    """Return (native, display, usdjpy, fx_failed) for a symbol/currency request."""
    ticker, _, _ = resolve_ticker(symbol, settings, market_hint=market_hint)
    native = native_currency_for_symbol(ticker)
    display = resolve_display_currency(
        currency,
        symbol=ticker,
        market_hint=market_hint,
        default_setting=settings.display_currency,
    )
    if display == native:
        return native, display, 1.0, False
    try:
        usdjpy = get_usdjpy_rate(settings.fx_usdjpy_manual)
        return native, display, usdjpy, False
    except Exception:
        return native, native, 1.0, True
