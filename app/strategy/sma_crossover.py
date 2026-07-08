from __future__ import annotations

from enum import Enum

import pandas as pd


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


def sma_signal_series(
    bars: pd.DataFrame,
    fast_period: int,
    slow_period: int,
) -> pd.Series:
    """Per-bar SMA crossover signals aligned with ``bars`` index."""
    if len(bars) < slow_period + 2:
        raise ValueError(
            f"Need at least {slow_period + 2} bars, got {len(bars)}"
        )

    close = bars["close"].astype(float)
    fast = close.rolling(fast_period).mean()
    slow = close.rolling(slow_period).mean()
    prev_fast = fast.shift(1)
    prev_slow = slow.shift(1)

    buy = (prev_fast <= prev_slow) & (fast > slow)
    sell = (prev_fast >= prev_slow) & (fast < slow)

    signals = pd.Series(Signal.HOLD.value, index=bars.index, dtype=object)
    signals[buy.fillna(False)] = Signal.BUY.value
    signals[sell.fillna(False)] = Signal.SELL.value
    return signals


def compute_sma_signal(
    bars: pd.DataFrame,
    fast_period: int,
    slow_period: int,
) -> Signal:
    """Return trade signal from the latest completed bar crossover."""
    series = sma_signal_series(bars, fast_period, slow_period)
    return Signal(series.iloc[-1])
