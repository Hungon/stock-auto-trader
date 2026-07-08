from __future__ import annotations

import time
from typing import Any, Literal

Currency = Literal["usd", "jpy"]

_fx_cache: tuple[float, float] | None = None  # (rate, monotonic_ts)
_FX_TTL_SECONDS = 300


def native_currency_for_market(market: str) -> Currency:
    return "jpy" if market == "jp" else "usd"


def native_currency_for_symbol(symbol: str) -> Currency:
    from app.markets.detect import is_japan_symbol

    return "jpy" if is_japan_symbol(symbol) else "usd"


def resolve_display_currency(
    requested: str | None,
    *,
    symbol: str,
    market_hint: str | None = None,
    default_setting: str,
) -> Currency:
    key = (requested or default_setting or "auto").strip().lower()
    if key == "auto":
        if market_hint in {"jp", "us"}:
            return native_currency_for_market(market_hint)
        return native_currency_for_symbol(symbol)
    if key in {"usd", "jpy"}:
        return key  # type: ignore[return-value]
    raise ValueError('Currency must be "usd", "jpy", or "auto"')


def get_usdjpy_rate(manual_rate: float | None = None) -> float:
    """Return how many JPY per 1 USD."""
    if manual_rate is not None and manual_rate > 0:
        return manual_rate

    global _fx_cache
    now = time.monotonic()
    if _fx_cache and now - _fx_cache[1] < _FX_TTL_SECONDS:
        return _fx_cache[0]

    import yfinance as yf

    hist = yf.Ticker("USDJPY=X").history(period="5d")
    if hist.empty:
        raise ValueError("Could not fetch USD/JPY rate (USDJPY=X)")
    rate = float(hist["Close"].iloc[-1] if "Close" in hist.columns else hist["close"].iloc[-1])
    _fx_cache = (rate, now)
    return rate


def convert_amount(
    amount: float,
    *,
    from_currency: Currency,
    to_currency: Currency,
    usdjpy: float,
) -> float:
    if from_currency == to_currency:
        return amount
    if from_currency == "usd" and to_currency == "jpy":
        return amount * usdjpy
    return amount / usdjpy


def build_conversion_info(
    *,
    native: Currency,
    display: Currency,
    usdjpy: float,
    native_close: float | None,
    applied: bool,
) -> dict[str, Any]:
    """Human-readable conversion breakdown for the UI."""
    if native_close is None:
        native_close = 0.0

    if not applied or native == display:
        return {
            "applied": False,
            "native_currency": native,
            "display_currency": display,
            "fx_usdjpy": usdjpy,
            "native_close": native_close,
            "display_close": native_close,
            "formula": f"No conversion — prices are already in {native.upper()}.",
            "example": None,
        }

    if native == "usd" and display == "jpy":
        display_close = convert_amount(
            native_close, from_currency="usd", to_currency="jpy", usdjpy=usdjpy
        )
        return {
            "applied": True,
            "native_currency": native,
            "display_currency": display,
            "fx_usdjpy": usdjpy,
            "native_close": native_close,
            "display_close": display_close,
            "formula": "display_price = native_price × USD/JPY",
            "example": (
                f"¥{display_close:,.0f} = ${native_close:,.2f} × {usdjpy:,.2f}"
            ),
        }

    display_close = convert_amount(
        native_close, from_currency="jpy", to_currency="usd", usdjpy=usdjpy
    )
    return {
        "applied": True,
        "native_currency": native,
        "display_currency": display,
        "fx_usdjpy": usdjpy,
        "native_close": native_close,
        "display_close": display_close,
        "formula": "display_price = native_price ÷ USD/JPY",
        "example": (
            f"${display_close:,.2f} = ¥{native_close:,.0f} ÷ {usdjpy:,.2f}"
        ),
    }


def format_money(amount: float, currency: Currency) -> str:
    if currency == "jpy":
        return f"¥{amount:,.0f}"
    return f"${amount:,.2f}"


def format_price(amount: float, currency: Currency) -> str:
    if currency == "jpy":
        return f"¥{amount:,.0f}"
    return f"${amount:,.2f}"
