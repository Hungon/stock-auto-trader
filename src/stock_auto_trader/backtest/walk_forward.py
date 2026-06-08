"""Walk-forward out-of-sample backtesting.

Splits a date range into rolling train/test windows and chains equity
across consecutive test periods (see ``stock-trader walk-forward``).
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from stock_auto_trader.backtest.engine import BacktestResult
from stock_auto_trader.backtest.run import execute_backtest
from stock_auto_trader.config import Settings
from stock_auto_trader.logging_config import log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalkForwardWindow:
    """Single out-of-sample test period and its backtest result."""

    window: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    result: BacktestResult


@dataclass(frozen=True)
class WalkForwardSummary:
    """Combined metrics across all walk-forward test windows."""

    number_of_windows: int
    total_return_pct: float
    annualized_return_pct: float | None
    max_drawdown_pct: float
    sharpe_ratio: float | None
    win_rate_pct: float | None
    profit_factor: float | None
    total_trades: int
    windows: list[WalkForwardWindow]


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    max_day = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, max_day))


def _generate_windows(
    start: date,
    end: date,
    *,
    train_years: int,
    test_months: int,
) -> list[tuple[date, date, date, date]]:
    windows: list[tuple[date, date, date, date]] = []
    train_start = start
    while True:
        train_end = _add_months(train_start, train_years * 12) - timedelta(days=1)
        test_start = train_end + timedelta(days=1)
        test_end = _add_months(test_start, test_months) - timedelta(days=1)
        if test_end > end:
            break
        windows.append((train_start, train_end, test_start, test_end))
        train_start = test_start
    return windows


def run_walk_forward(
    settings: Settings,
    *,
    symbol: str,
    strategy_id: str,
    start: date,
    end: date,
    train_years: int = 3,
    test_months: int = 6,
    initial_cash: float | None = None,
    market_hint: str | None = None,
) -> WalkForwardSummary:
    """Run rolling out-of-sample backtests and aggregate window metrics."""
    log_event(
        logger,
        "walk_forward_started",
        symbol=symbol,
        strategy=strategy_id,
        start=str(start),
        end=str(end),
        train_years=train_years,
        test_months=test_months,
    )

    window_specs = _generate_windows(
        start, end, train_years=train_years, test_months=test_months
    )
    if not window_specs:
        raise ValueError(
            f"No walk-forward windows fit in {start} → {end} "
            f"with train={train_years}y test={test_months}m"
        )

    completed: list[WalkForwardWindow] = []
    cash = initial_cash if initial_cash is not None else settings.backtest_initial_cash

    for i, (train_start, train_end, test_start, test_end) in enumerate(window_specs, 1):
        result, _, _mkt, _ = execute_backtest(
            settings,
            symbol=symbol,
            start=test_start,
            end=test_end,
            initial_cash=cash,
            market_hint=market_hint,
            strategy_id=strategy_id,
        )
        cash = result.final_equity
        wf = WalkForwardWindow(
            window=i,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            result=result,
        )
        completed.append(wf)
        log_event(
            logger,
            "walk_forward_window_completed",
            window=i,
            test_start=str(test_start),
            test_end=str(test_end),
            return_pct=result.total_return_pct,
            trades=result.num_trades,
        )

    first_cash = completed[0].result.initial_cash
    final_equity = completed[-1].result.final_equity
    total_return_pct = (final_equity / first_cash - 1.0) * 100.0

    years = max((end - start).days / 365.25, 0.01)
    annualized = ((final_equity / first_cash) ** (1.0 / years) - 1.0) * 100.0

    max_dd = min(w.result.max_drawdown_pct for w in completed)
    sharpes = [w.result.sharpe_ratio for w in completed if w.result.sharpe_ratio is not None]
    sharpe = sum(sharpes) / len(sharpes) if sharpes else None
    win_rates = [
        w.result.win_rate_pct for w in completed if w.result.win_rate_pct is not None
    ]
    win_rate = sum(win_rates) / len(win_rates) if win_rates else None
    pfs = [w.result.profit_factor for w in completed if w.result.profit_factor is not None]
    profit_factor = sum(pfs) / len(pfs) if pfs else None
    total_trades = sum(w.result.num_trades for w in completed)

    summary = WalkForwardSummary(
        number_of_windows=len(completed),
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized,
        max_drawdown_pct=max_dd,
        sharpe_ratio=sharpe,
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
        total_trades=total_trades,
        windows=completed,
    )

    log_event(
        logger,
        "walk_forward_completed",
        windows=summary.number_of_windows,
        total_return_pct=summary.total_return_pct,
        total_trades=summary.total_trades,
    )
    return summary
