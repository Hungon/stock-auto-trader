"""Detect stale market data before live or paper orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from stock_auto_trader.config import Settings


@dataclass(frozen=True)
class StaleDataCheck:
    """Whether the latest bar is too old for the configured timeframe."""

    stale: bool
    symbol: str
    latest_bar_time: datetime | None
    now: datetime
    max_age_seconds: int
    reason: str = ""


def _default_max_age_seconds(timeframe: str) -> int:
    mapping = {
        "1Min": 120,
        "5Min": 600,
        "15Min": 1800,
        "1Hour": 7200,
        "1Day": 0,  # use daily bar age instead
    }
    return mapping.get(timeframe, 900)


def _is_daily_timeframe(timeframe: str) -> bool:
    return timeframe in {"1Day", "1D", "Day"}


def _count_trading_days_back(from_date: datetime, days: int) -> datetime:
    """Approximate trading days by skipping weekends."""
    current = from_date
    remaining = days
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def check_stale_data(
    settings: Settings,
    symbol: str,
    bars: pd.DataFrame,
) -> StaleDataCheck:
    """Compare latest bar timestamp to MAX_DATA_AGE_SECONDS or MAX_DAILY_BAR_AGE_DAYS."""
    now = datetime.now(timezone.utc)
    if bars.empty:
        return StaleDataCheck(
            stale=True,
            symbol=symbol,
            latest_bar_time=None,
            now=now,
            max_age_seconds=0,
            reason="no_bars",
        )

    latest_ts = bars.index[-1]
    if hasattr(latest_ts, "to_pydatetime"):
        latest_dt = latest_ts.to_pydatetime()
    else:
        latest_dt = latest_ts
    if latest_dt.tzinfo is None:
        latest_dt = latest_dt.replace(tzinfo=timezone.utc)

    if _is_daily_timeframe(settings.bar_timeframe):
        max_days = settings.max_daily_bar_age_days
        cutoff = _count_trading_days_back(now, max_days + 5)
        if latest_dt < cutoff:
            return StaleDataCheck(
                stale=True,
                symbol=symbol,
                latest_bar_time=latest_dt,
                now=now,
                max_age_seconds=max_days * 86400,
                reason=(
                    f"latest daily bar {latest_dt.date()} is older than "
                    f"{max_days} trading days"
                ),
            )
        return StaleDataCheck(
            stale=False,
            symbol=symbol,
            latest_bar_time=latest_dt,
            now=now,
            max_age_seconds=max_days * 86400,
        )

    max_age = settings.max_data_age_seconds
    if max_age <= 0:
        max_age = _default_max_age_seconds(settings.bar_timeframe)

    age_seconds = (now - latest_dt).total_seconds()
    if age_seconds > max_age:
        return StaleDataCheck(
            stale=True,
            symbol=symbol,
            latest_bar_time=latest_dt,
            now=now,
            max_age_seconds=max_age,
            reason=f"bar age {age_seconds:.0f}s exceeds limit {max_age}s",
        )

    return StaleDataCheck(
        stale=False,
        symbol=symbol,
        latest_bar_time=latest_dt,
        now=now,
        max_age_seconds=max_age,
    )
