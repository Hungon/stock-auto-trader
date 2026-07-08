"""Backtest fill pricing: slippage, commission, and execution timing.

Execution modes control when signal-based fills occur relative to the bar
that generated the signal (see BACKTEST_EXECUTION_MODE in .env).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionMode(str, Enum):
    """When a simulated order fills relative to its signal bar."""

    SAME_CLOSE = "same_close"
    NEXT_OPEN = "next_open"
    NEXT_CLOSE = "next_close"


@dataclass(frozen=True)
class FillParams:
    """Slippage, commission, and execution assumptions for backtests."""

    slippage_bps: float = 0.0
    commission_per_trade: float = 0.0
    commission_bps: float = 0.0
    execution_mode: str = "next_open"


def apply_slippage(base_price: float, side: str, slippage_bps: float) -> float:
    """Worsen fill price by *slippage_bps* (buys pay more, sells receive less)."""
    if slippage_bps <= 0:
        return base_price
    factor = slippage_bps / 10_000.0
    if side == "buy":
        return base_price * (1.0 + factor)
    return base_price * (1.0 - factor)


def calc_commission(
    notional: float,
    *,
    commission_per_trade: float,
    commission_bps: float,
) -> float:
    """Flat per-trade fee plus basis-points on notional."""
    return commission_per_trade + notional * commission_bps / 10_000.0


def fill_price_for_bar(
    row,
    side: str,
    execution_mode: str,
    *,
    is_entry_from_signal: bool,
) -> float:
    """Resolve fill price based on execution mode."""
    mode = ExecutionMode(execution_mode)
    if mode == ExecutionMode.SAME_CLOSE or not is_entry_from_signal:
        return float(row["close"])
    if mode == ExecutionMode.NEXT_OPEN:
        return float(row["open"])
    return float(row["close"])
