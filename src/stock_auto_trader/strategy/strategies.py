from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from stock_auto_trader.backtest.engine import BacktestResult, build_backtest_result
from stock_auto_trader.backtest.execution import FillParams
from stock_auto_trader.backtest.simulator import simulate_long_only
from stock_auto_trader.strategy.indicators import (
    average_volume,
    highest_high,
    rsi,
    sma,
)
from stock_auto_trader.strategy.signals import cross_above, cross_below, rising
from stock_auto_trader.strategy.sma_crossover import Signal, sma_signal_series


@dataclass(frozen=True)
class StrategySpec:
    id: str
    name: str
    description: str
    min_bars: int
    supported: bool = True
    run: Callable[..., BacktestResult] | None = None


def _prep(bars: pd.DataFrame) -> pd.DataFrame:
    b = bars.sort_index().copy()
    close = b["close"].astype(float)
    high = b["high"].astype(float)
    vol = b["volume"].astype(float)
    b["_close"] = close
    b["_high"] = high
    b["_vol"] = vol
    b["_ma10"] = sma(close, 10)
    b["_ma20"] = sma(close, 20)
    b["_ma50"] = sma(close, 50)
    b["_ma200"] = sma(close, 200)
    b["_rsi14"] = rsi(close, 14)
    b["_vol_avg20"] = average_volume(vol, 20)
    b["_high20"] = highest_high(high, 20)
    return b


def _simulate_and_build(
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    entry_signal: pd.Series,
    exit_signal: pd.Series,
    strategy_id: str,
    fill_params: FillParams | None = None,
    market: str = "us",
    **sim_kwargs,
) -> BacktestResult:
    fp = fill_params or FillParams()
    trades, equity_pts, equity_idx, total_commission = simulate_long_only(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        max_order_notional=max_order_notional,
        max_position_shares=max_position_shares,
        entry_signal=entry_signal,
        exit_signal=exit_signal,
        fill_params=fp,
        strategy_id=strategy_id,
        market=market,
        **sim_kwargs,
    )
    return build_backtest_result(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        trades=trades,
        equity_points=equity_pts,
        equity_index=equity_idx,
        strategy_id=strategy_id,
        fill_params=fp,
        total_commission=total_commission,
    )


def run_sma_crossover(
    bars: pd.DataFrame,
    *,
    symbol: str,
    fast_period: int,
    slow_period: int,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    fill_params: FillParams | None = None,
    market: str = "us",
) -> BacktestResult:
    signals = sma_signal_series(bars, fast_period, slow_period)
    b = _prep(bars)
    entry = (signals == Signal.BUY.value) & (b["_vol"] > b["_vol_avg20"])
    exit_ = signals == Signal.SELL.value
    return _simulate_and_build(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        max_order_notional=max_order_notional,
        max_position_shares=max_position_shares,
        entry_signal=entry,
        exit_signal=exit_,
        strategy_id="sma_crossover",
        fill_params=fill_params,
        market=market,
        stop_loss_pct=0.06,
        trailing_stop_pct=0.1,
        min_hold_bars=3,
    )


def run_ma_cross_20_50(
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    **_kwargs,
) -> BacktestResult:
    """Golden cross 20/50 with trend and volume filters."""
    b = _prep(bars)
    entry = (
        cross_above(b["_ma20"], b["_ma50"])
        & (b["_close"] > b["_ma200"])
        & rising(b["_ma50"])
        & (b["_vol"] > b["_vol_avg20"])
    )
    exit_ = cross_below(b["_ma20"], b["_ma50"]) | (b["_close"] < b["_ma200"])
    return _simulate_and_build(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        max_order_notional=max_order_notional,
        max_position_shares=max_position_shares,
        entry_signal=entry,
        exit_signal=exit_,
        strategy_id="ma_cross_20_50",
        fill_params=_kwargs.get("fill_params"),
        market=_kwargs.get("market", "us"),
        stop_loss_pct=0.05,
        trailing_stop_pct=0.12,
        take_profit_pct=0.25,
        min_hold_bars=5,
    )


def run_ma_trend_20_50(
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    **_kwargs,
) -> BacktestResult:
    """Enter on 20/50 golden cross above MA200; exit on death cross."""
    b = _prep(bars)
    entry = (
        cross_above(b["_ma20"], b["_ma50"])
        & (b["_close"] > b["_ma200"])
        & (b["_vol"] > b["_vol_avg20"])
        & rising(b["_ma50"], 10)
    )
    exit_ = cross_below(b["_ma20"], b["_ma50"])
    return _simulate_and_build(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        max_order_notional=max_order_notional,
        max_position_shares=max_position_shares,
        entry_signal=entry,
        exit_signal=exit_,
        strategy_id="ma_trend_20_50",
        fill_params=_kwargs.get("fill_params"),
        market=_kwargs.get("market", "us"),
        stop_loss_pct=0.05,
        trailing_stop_pct=0.1,
        min_hold_bars=5,
    )


def run_rsi_mean_reversion(
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    **_kwargs,
) -> BacktestResult:
    """Oversold bounce above MA200; take profit and stops."""
    b = _prep(bars)
    oversold = b["_rsi14"] < 32
    turning_up = b["_rsi14"] > b["_rsi14"].shift(1)
    entry = oversold & turning_up & (b["_close"] > b["_ma200"])
    exit_ = b["_rsi14"] > 58
    return _simulate_and_build(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        max_order_notional=max_order_notional,
        max_position_shares=max_position_shares,
        entry_signal=entry,
        exit_signal=exit_,
        strategy_id="rsi_mean_reversion",
        fill_params=_kwargs.get("fill_params"),
        market=_kwargs.get("market", "us"),
        stop_loss_pct=0.05,
        take_profit_pct=0.12,
        max_hold_bars=15,
        min_hold_bars=3,
    )


def run_breakout_20(
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    **_kwargs,
) -> BacktestResult:
    """Breakout above 20d high in an uptrend; trail winners."""
    b = _prep(bars)
    prior_high20 = b["_high20"].shift(1)
    breakout = (b["_close"] > prior_high20) & (b["_close"].shift(1) <= prior_high20.shift(1))
    entry = (
        breakout
        & (b["_vol"] > 1.5 * b["_vol_avg20"])
        & (b["_close"] > b["_ma50"])
        & (b["_ma20"] > b["_ma50"])
    )
    exit_ = b["_close"] < b["_ma20"]
    return _simulate_and_build(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        max_order_notional=max_order_notional,
        max_position_shares=max_position_shares,
        entry_signal=entry,
        exit_signal=exit_,
        strategy_id="breakout_20",
        fill_params=_kwargs.get("fill_params"),
        market=_kwargs.get("market", "us"),
        trailing_stop_pct=0.1,
        take_profit_pct=0.2,
        min_hold_bars=3,
        track_breakout_level=prior_high20,
    )


def run_trend_risk_control(
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    **_kwargs,
) -> BacktestResult:
    """Trend + RSI band + volume; layered exits."""
    b = _prep(bars)
    rsi_ok = (b["_rsi14"] >= 45) & (b["_rsi14"] <= 68)
    entry = (
        cross_above(b["_ma20"], b["_ma50"])
        & (b["_close"] > b["_ma200"])
        & rsi_ok
        & (b["_vol"] > b["_vol_avg20"])
    )
    exit_ = cross_below(b["_ma20"], b["_ma50"]) | (b["_close"] < b["_ma200"])
    return _simulate_and_build(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        max_order_notional=max_order_notional,
        max_position_shares=max_position_shares,
        entry_signal=entry,
        exit_signal=exit_,
        strategy_id="trend_risk_control",
        fill_params=_kwargs.get("fill_params"),
        market=_kwargs.get("market", "us"),
        stop_loss_pct=0.04,
        trailing_stop_pct=0.12,
        take_profit_pct=0.22,
        min_hold_bars=5,
    )


STRATEGIES: dict[str, StrategySpec] = {
    "sma_crossover": StrategySpec(
        id="sma_crossover",
        name="SMA Crossover (config)",
        description="Fast/slow cross from .env + volume; 6% stop, 10% trail.",
        min_bars=32,
        run=run_sma_crossover,
    ),
    "ma_cross_20_50": StrategySpec(
        id="ma_cross_20_50",
        name="MA Cross 20/50 (filtered)",
        description="Golden cross with MA200 + rising MA50; 5% stop, 12% trail, 25% TP.",
        min_bars=202,
        run=run_ma_cross_20_50,
    ),
    "ma_trend_20_50": StrategySpec(
        id="ma_trend_20_50",
        name="MA Trend 20/50",
        description="Golden/death cross above MA200 with volume filter.",
        min_bars=202,
        run=run_ma_trend_20_50,
    ),
    "rsi_mean_reversion": StrategySpec(
        id="rsi_mean_reversion",
        name="RSI Mean Reversion",
        description="RSI<32 turning up above MA200; 12% TP, 5% stop.",
        min_bars=202,
        run=run_rsi_mean_reversion,
    ),
    "breakout_20": StrategySpec(
        id="breakout_20",
        name="Breakout (20-day high)",
        description="New 20d high + volume in uptrend; 10% trail, 20% TP.",
        min_bars=202,
        run=run_breakout_20,
    ),
    "trend_risk_control": StrategySpec(
        id="trend_risk_control",
        name="Trend + Risk Control",
        description="Cross + MA200 + RSI 45–68 + volume; stops and 22% TP.",
        min_bars=202,
        run=run_trend_risk_control,
    ),
    "pair_trading": StrategySpec(
        id="pair_trading",
        name="Pair Trading (spread)",
        description="Needs two symbols — not run on single-ticker backtest.",
        min_bars=0,
        supported=False,
        run=None,
    ),
    "multi_factor": StrategySpec(
        id="multi_factor",
        name="Multi-Factor Ranking",
        description="Needs stock universe — portfolio mode not in this backtest.",
        min_bars=0,
        supported=False,
        run=None,
    ),
}


def list_strategies() -> list[dict]:
    out = []
    for spec in STRATEGIES.values():
        out.append(
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "min_bars": spec.min_bars,
                "supported": spec.supported,
            }
        )
    return sorted(out, key=lambda x: (not x["supported"], x["name"]))


def get_strategy(strategy_id: str) -> StrategySpec:
    key = strategy_id.strip().lower()
    if key not in STRATEGIES:
        supported = ", ".join(s.id for s in STRATEGIES.values() if s.supported)
        raise ValueError(f"Unknown strategy {strategy_id!r}. Choose from: {supported}")
    return STRATEGIES[key]


def run_strategy(
    strategy_id: str,
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    fast_period: int = 10,
    slow_period: int = 30,
    fill_params: FillParams | None = None,
    market: str = "us",
) -> BacktestResult:
    spec = get_strategy(strategy_id)
    if not spec.supported or spec.run is None:
        raise ValueError(f"Strategy {strategy_id!r} is not supported for single-symbol backtest.")
    if strategy_id == "sma_crossover":
        return run_sma_crossover(
            bars,
            symbol=symbol,
            fast_period=fast_period,
            slow_period=slow_period,
            initial_cash=initial_cash,
            max_order_notional=max_order_notional,
            max_position_shares=max_position_shares,
            fill_params=fill_params,
            market=market,
        )
    return spec.run(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        max_order_notional=max_order_notional,
        max_position_shares=max_position_shares,
        fill_params=fill_params,
        market=market,
    )
