from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from stock_auto_trader.backtest.data import fetch_bars_for_backtest, load_bars_from_csv
from stock_auto_trader.backtest.engine import BacktestResult
from stock_auto_trader.strategy.strategies import get_strategy, run_strategy
from stock_auto_trader.backtest.market_params import (
    resolve_backtest_limits,
    resolve_initial_cash,
    resolve_market_hint,
)
from stock_auto_trader.broker.alpaca import AlpacaBroker
from stock_auto_trader.config import Settings
from stock_auto_trader.data.bars_util import sanitize_bars
from stock_auto_trader.data.fetch import resolve_ticker


def load_backtest_bars(
    settings: Settings,
    *,
    symbol: str,
    start: date,
    end: date,
    market_hint: str | None = None,
    csv_path: Path | None = None,
) -> tuple[pd.DataFrame, str, str, str | None]:
    hint = resolve_market_hint(settings, market_hint)
    sym, mkt, alias_note = resolve_ticker(symbol, settings, market_hint=hint)
    if csv_path:
        bars = load_bars_from_csv(csv_path)
        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        bars = bars[(bars.index >= start_ts) & (bars.index < end_ts)]
    else:
        broker = AlpacaBroker(settings) if mkt == "us" else None
        bars = fetch_bars_for_backtest(
            settings, broker, sym, start, end, market_hint=hint
        )
    bars = sanitize_bars(bars)
    if bars.empty:
        raise ValueError(f"No complete price data for {sym} in range")
    return bars, sym, mkt, alias_note


def execute_backtest(
    settings: Settings,
    *,
    symbol: str,
    start: date,
    end: date,
    initial_cash: float | None = None,
    market_hint: str | None = None,
    csv_path: Path | None = None,
    strategy_id: str = "sma_crossover",
) -> tuple[BacktestResult, str, str, str | None]:
    """Run backtest; returns (result, resolved_symbol, market, alias_note)."""
    spec = get_strategy(strategy_id)
    bars, sym, mkt, alias_note = load_backtest_bars(
        settings,
        symbol=symbol,
        start=start,
        end=end,
        market_hint=market_hint,
        csv_path=csv_path,
    )
    cash = resolve_initial_cash(settings, mkt, initial_cash)
    ref_price = float(bars["close"].dropna().iloc[-1])
    max_notional, max_shares = resolve_backtest_limits(
        settings, mkt, cash, price=ref_price
    )

    min_bars = max(spec.min_bars, settings.slow_sma_period + 2)
    if len(bars) < min_bars:
        raise ValueError(
            f"Only {len(bars)} bars in range; need at least {min_bars} for "
            f"{spec.name}."
        )

    result = run_strategy(
        strategy_id,
        bars,
        symbol=sym,
        initial_cash=cash,
        max_order_notional=max_notional,
        max_position_shares=max_shares,
        fast_period=settings.fast_sma_period,
        slow_period=settings.slow_sma_period,
    )
    return result, sym, mkt, alias_note


def execute_backtest_compare(
    settings: Settings,
    *,
    symbol: str,
    start: date,
    end: date,
    initial_cash: float | None = None,
    market_hint: str | None = None,
    csv_path: Path | None = None,
) -> tuple[list[BacktestResult], str, str, str | None, list[dict]]:
    """Run all supported strategies on the same bars."""
    from stock_auto_trader.strategy.strategies import STRATEGIES

    bars, sym, mkt, alias_note = load_backtest_bars(
        settings,
        symbol=symbol,
        start=start,
        end=end,
        market_hint=market_hint,
        csv_path=csv_path,
    )
    cash = resolve_initial_cash(settings, mkt, initial_cash)
    ref_price = float(bars["close"].dropna().iloc[-1])
    max_notional, max_shares = resolve_backtest_limits(
        settings, mkt, cash, price=ref_price
    )

    results: list[BacktestResult] = []
    errors: list[dict] = []
    for spec in STRATEGIES.values():
        if not spec.supported:
            continue
        if len(bars) < spec.min_bars:
            errors.append(
                {
                    "strategy_id": spec.id,
                    "strategy_name": spec.name,
                    "error": f"Need at least {spec.min_bars} bars, got {len(bars)}",
                }
            )
            continue
        try:
            r = run_strategy(
                spec.id,
                bars,
                symbol=sym,
                initial_cash=cash,
                max_order_notional=max_notional,
                max_position_shares=max_shares,
                fast_period=settings.fast_sma_period,
                slow_period=settings.slow_sma_period,
            )
            results.append(r)
        except Exception as exc:
            errors.append(
                {
                    "strategy_id": spec.id,
                    "strategy_name": spec.name,
                    "error": str(exc),
                }
            )

    if not results and errors:
        raise ValueError(errors[0]["error"])
    return results, sym, mkt, alias_note, errors


def execute_backtest_scan(
    settings: Settings,
    *,
    symbols: list[str],
    start: date,
    end: date,
    initial_cash: float | None = None,
) -> list[dict]:
    """Run compare-all for each symbol; return summary rows sorted by best return."""
    from stock_auto_trader.markets.detect import is_japan_symbol

    rows: list[dict] = []
    for raw in symbols:
        sym_input = raw.strip().upper()
        if not sym_input:
            continue
        hint = "jp" if is_japan_symbol(sym_input) else "us"
        try:
            results, resolved, mkt, _, errors = execute_backtest_compare(
                settings,
                symbol=sym_input,
                start=start,
                end=end,
                initial_cash=initial_cash,
                market_hint=hint,
            )
            if not results:
                rows.append(
                    {
                        "symbol": sym_input,
                        "data_symbol": resolved,
                        "market": mkt,
                        "error": errors[0]["error"] if errors else "no results",
                    }
                )
                continue
            best = max(results, key=lambda r: r.total_return_pct)
            for r in sorted(results, key=lambda x: -x.total_return_pct):
                from stock_auto_trader.strategy.strategies import STRATEGIES

                spec = STRATEGIES.get(r.strategy_id)
                rows.append(
                    {
                        "symbol": sym_input,
                        "data_symbol": resolved,
                        "market": mkt,
                        "strategy_id": r.strategy_id,
                        "strategy_name": spec.name if spec else r.strategy_id,
                        "total_return_pct": r.total_return_pct,
                        "buy_hold_return_pct": r.buy_hold_return_pct,
                        "max_drawdown_pct": r.max_drawdown_pct,
                        "win_rate_pct": r.win_rate_pct,
                        "num_trades": r.num_trades,
                        "sharpe_ratio": r.sharpe_ratio,
                        "profit_factor": r.profit_factor,
                        "is_best_for_symbol": r.strategy_id == best.strategy_id,
                    }
                )
        except Exception as exc:
            rows.append({"symbol": sym_input, "error": str(exc)})
    rows.sort(
        key=lambda x: (x.get("total_return_pct") is None, -(x.get("total_return_pct") or -999)),
    )
    return rows


def default_backtest_range() -> tuple[date, date]:
    # Exclude today: Yahoo/Alpaca often have incomplete OHLCV for the current session.
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365 * 2)
    return start, end
