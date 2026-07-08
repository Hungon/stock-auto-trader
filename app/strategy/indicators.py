from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def highest_high(high: pd.Series, period: int) -> pd.Series:
    return high.rolling(period).max()


def average_volume(volume: pd.Series, period: int) -> pd.Series:
    return volume.rolling(period).mean()
