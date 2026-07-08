"""Backtesting service: single/compare/scan runs and result serialization."""

from __future__ import annotations

from app.backtest.market_params import resolve_initial_cash
from app.backtest.run import (
    default_backtest_range,
    execute_backtest,
    execute_backtest_compare,
    execute_backtest_scan,
)
from app.backtest.serialize import result_to_dict
from app.strategy.strategies import list_strategies

__all__ = [
    "resolve_initial_cash",
    "default_backtest_range",
    "execute_backtest",
    "execute_backtest_compare",
    "execute_backtest_scan",
    "result_to_dict",
    "list_strategies",
]
