from __future__ import annotations

import pandas as pd

from stock_auto_trader.backtest.engine import run_backtest
from stock_auto_trader.backtest.market_params import (
    resolve_backtest_limits,
    resolve_initial_cash,
)
from stock_auto_trader.config import Settings
from stock_auto_trader.strategy.sma_crossover import Signal, sma_signal_series


def _bar_time(ts) -> str:
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%d")
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def build_chart_payload(
    bars: pd.DataFrame,
    *,
    symbol: str,
    settings: Settings,
    market: str = "us",
    include_backtest_trades: bool = True,
) -> dict:
    bars = bars.sort_index()
    close = bars["close"].astype(float)
    fast = close.rolling(settings.fast_sma_period).mean()
    slow = close.rolling(settings.slow_sma_period).mean()
    signals = sma_signal_series(
        bars, settings.fast_sma_period, settings.slow_sma_period
    )

    candles = []
    volume = []
    fast_sma = []
    slow_sma = []
    markers = []

    for ts, row in bars.iterrows():
        t = _bar_time(ts)
        o, h, l, c = (
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
        )
        candles.append({"time": t, "open": o, "high": h, "low": l, "close": c})
        volume.append(
            {
                "time": t,
                "value": float(row["volume"]),
                "color": "rgba(38,166,154,0.5)" if c >= o else "rgba(239,83,80,0.5)",
            }
        )
        fv, sv = fast.loc[ts], slow.loc[ts]
        if not pd.isna(fv):
            fast_sma.append({"time": t, "value": float(fv)})
        if not pd.isna(sv):
            slow_sma.append({"time": t, "value": float(sv)})

        sig = signals.loc[ts]
        if sig == Signal.BUY.value:
            markers.append(
                {
                    "time": t,
                    "position": "belowBar",
                    "color": "#26a69a",
                    "shape": "arrowUp",
                    "text": "BUY",
                }
            )
        elif sig == Signal.SELL.value:
            markers.append(
                {
                    "time": t,
                    "position": "aboveBar",
                    "color": "#ef5350",
                    "shape": "arrowDown",
                    "text": "SELL",
                }
            )

    trades = []
    stats = None
    if include_backtest_trades and len(bars) >= settings.slow_sma_period + 2:
        cash = resolve_initial_cash(settings, market, None)
        ref_price = float(bars["close"].dropna().iloc[-1])
        max_notional, max_shares = resolve_backtest_limits(
            settings, market, cash, price=ref_price
        )
        result = run_backtest(
            bars,
            symbol=symbol,
            fast_period=settings.fast_sma_period,
            slow_period=settings.slow_sma_period,
            initial_cash=cash,
            max_order_notional=max_notional,
            max_position_shares=max_shares,
        )
        for trade in result.trades:
            trades.append(
                {
                    "time": _bar_time(trade.timestamp),
                    "side": trade.side,
                    "qty": trade.qty,
                    "price": trade.price,
                }
            )
        stats = {
            "total_return_pct": round(result.total_return_pct, 2),
            "buy_hold_return_pct": round(result.buy_hold_return_pct, 2),
            "max_drawdown_pct": round(result.max_drawdown_pct, 2),
            "num_trades": result.num_trades,
        }

    last = candles[-1] if candles else None
    return {
        "symbol": symbol,
        "fast_period": settings.fast_sma_period,
        "slow_period": settings.slow_sma_period,
        "bar_timeframe": settings.bar_timeframe,
        "candles": candles,
        "volume": volume,
        "fast_sma": fast_sma,
        "slow_sma": slow_sma,
        "markers": markers,
        "trades": trades,
        "stats": stats,
        "last": last,
    }
