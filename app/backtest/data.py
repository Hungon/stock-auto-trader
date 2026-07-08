from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path

import pandas as pd

from app.broker.alpaca import AlpacaBroker
from app.core.config import Settings
from app.data.fetch import fetch_bars_between as _fetch_bars

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def load_bars_from_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp")
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], utc=True)
        df = df.set_index("date")
    elif not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("CSV needs a 'timestamp' or 'date' column, or a datetime index")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    return df.sort_index()[REQUIRED_COLUMNS]


def fetch_bars_for_backtest(
    settings: Settings,
    broker: AlpacaBroker | None,
    symbol: str,
    start: date,
    end: date,
    *,
    market_hint: str | None = None,
) -> pd.DataFrame:
    return _fetch_bars(
        settings, symbol, start, end, broker=broker, market_hint=market_hint
    )
