"""US market session checks using Alpaca clock data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class MarketHoursCheck:
    """Whether trading is allowed under REQUIRE_MARKET_OPEN and session buffers."""

    allowed: bool
    reason: str = ""
    is_open: bool = False
    in_premarket: bool = False
    in_afterhours: bool = False


@dataclass(frozen=True)
class MarketClockInfo:
    """Normalized Alpaca clock fields for market-hours evaluation."""

    is_open: bool
    next_open: datetime | None
    next_close: datetime | None
    timestamp: datetime


def evaluate_market_hours(
    clock: MarketClockInfo,
    *,
    require_market_open: bool,
    allow_premarket: bool,
    allow_afterhours: bool,
    no_trade_first_minutes: int,
    no_trade_last_minutes: int,
) -> MarketHoursCheck:
    """Apply pre/after-hours and open/close buffer rules to *clock*."""
    now = clock.timestamp
    if clock.timestamp.tzinfo is None:
        now = clock.timestamp.replace(tzinfo=timezone.utc)

    in_premarket = False
    in_afterhours = False
    if clock.next_open and clock.next_close:
        if not clock.is_open and now < clock.next_open:
            in_premarket = True
        if not clock.is_open and clock.next_close and now > clock.next_close:
            in_afterhours = True

    if not require_market_open:
        return MarketHoursCheck(
            allowed=True,
            is_open=clock.is_open,
            in_premarket=in_premarket,
            in_afterhours=in_afterhours,
        )

    if clock.is_open:
        if no_trade_first_minutes > 0 and clock.next_close:
            session_open = clock.next_close - timedelta(hours=6, minutes=30)
            minutes_since_open = (now - session_open).total_seconds() / 60.0
            if 0 <= minutes_since_open < no_trade_first_minutes:
                return MarketHoursCheck(
                    allowed=False,
                    reason=(
                        f"within first {no_trade_first_minutes} minutes after open"
                    ),
                    is_open=True,
                )
        if no_trade_last_minutes > 0 and clock.next_close:
            minutes_to_close = (clock.next_close - now).total_seconds() / 60.0
            if 0 <= minutes_to_close < no_trade_last_minutes:
                return MarketHoursCheck(
                    allowed=False,
                    reason=(
                        f"within last {no_trade_last_minutes} minutes before close"
                    ),
                    is_open=True,
                )
        return MarketHoursCheck(allowed=True, is_open=True)

    if in_premarket and allow_premarket:
        return MarketHoursCheck(
            allowed=True,
            is_open=False,
            in_premarket=True,
        )
    if in_afterhours and allow_afterhours:
        return MarketHoursCheck(
            allowed=True,
            is_open=False,
            in_afterhours=True,
        )

    return MarketHoursCheck(
        allowed=False,
        reason="market is closed",
        is_open=False,
        in_premarket=in_premarket,
        in_afterhours=in_afterhours,
    )
