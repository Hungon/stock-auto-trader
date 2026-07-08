from __future__ import annotations

import pandas as pd

OHLCV = ["open", "high", "low", "close", "volume"]


def sanitize_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Drop incomplete rows (e.g. today's NaN close from Yahoo before market close)."""
    if df.empty:
        return df
    cols = [c for c in OHLCV if c in df.columns]
    out = df.sort_index().copy()
    out = out.dropna(subset=cols)
    if "close" in out.columns:
        out = out[out["close"] > 0]
    return out
