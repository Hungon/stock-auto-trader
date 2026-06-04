from __future__ import annotations

from stock_auto_trader.config import Settings

# Defaults when .env still uses US-scale numbers (e.g. MAX_ORDER_NOTIONAL=500).
_JP_DEFAULT_INITIAL_CASH = 1_000_000.0
_JP_DEFAULT_MAX_NOTIONAL = 500_000.0
_US_SCALE_NOTIONAL_CEILING = 10_000.0


def resolve_market_hint(settings: Settings, market_hint: str | None) -> str | None:
    if market_hint:
        return market_hint
    m = (settings.market or "auto").strip().lower()
    return None if m == "auto" else m


def resolve_initial_cash(
    settings: Settings,
    market: str,
    override: float | None,
) -> float:
    if override is not None:
        return override
    if market == "jp":
        if settings.backtest_initial_cash_jpy is not None:
            return settings.backtest_initial_cash_jpy
        if settings.backtest_initial_cash <= 50_000:
            return _JP_DEFAULT_INITIAL_CASH
        return settings.backtest_initial_cash
    return settings.backtest_initial_cash


def resolve_backtest_limits(
    settings: Settings,
    market: str,
    initial_cash: float,
    *,
    price: float | None = None,
) -> tuple[float, int]:
    """Position caps for backtest (deploy most of equity when price is known)."""
    shares = settings.max_position_shares
    notional = settings.max_order_notional

    if market == "jp":
        if settings.backtest_max_order_notional_jpy is not None:
            notional = settings.backtest_max_order_notional_jpy
        elif settings.max_order_notional < _US_SCALE_NOTIONAL_CEILING:
            notional = min(_JP_DEFAULT_MAX_NOTIONAL, initial_cash * 0.95)
    elif initial_cash > 0 and notional < initial_cash * 0.5:
        notional = min(initial_cash * 0.95, max(notional, initial_cash * 0.95))

    if price is not None and price > 0:
        max_by_cash = int(initial_cash * 0.95 / price)
        shares = max(shares, max_by_cash)
    notional = max(notional, initial_cash * 0.95) if initial_cash > 0 else notional
    return notional, shares
