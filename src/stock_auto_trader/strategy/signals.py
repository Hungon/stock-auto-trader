from __future__ import annotations

import pandas as pd


def cross_above(fast: pd.Series, slow: pd.Series) -> pd.Series:
    prev_fast = fast.shift(1)
    prev_slow = slow.shift(1)
    return (fast > slow) & (prev_fast <= prev_slow)


def cross_below(fast: pd.Series, slow: pd.Series) -> pd.Series:
    prev_fast = fast.shift(1)
    prev_slow = slow.shift(1)
    return (fast < slow) & (prev_fast >= prev_slow)


def rising(series: pd.Series, lookback: int = 5) -> pd.Series:
    return series > series.shift(lookback)
