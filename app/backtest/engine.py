from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from app.backtest.execution import FillParams, apply_slippage, calc_commission
from app.strategy.sma_crossover import Signal, sma_signal_series


@dataclass(frozen=True)
class Trade:
    """Single simulated or exported fill with journal metadata."""

    timestamp: datetime
    side: str
    price: float
    qty: int
    cash_after: float
    commission: float = 0.0
    slippage_bps: float = 0.0
    execution_mode: str = "same_close"
    reason: str = ""
    position_after: int = 0
    equity_after: float = 0.0
    realized_pnl: float | None = None
    strategy_id: str = ""
    market: str = "us"

    @property
    def notional(self) -> float:
        """Fill notional in account currency."""
        return self.price * self.qty


@dataclass(frozen=True)
class BacktestResult:
    """Summary metrics and trade list for one backtest run."""

    symbol: str
    start: datetime
    end: datetime
    initial_cash: float
    final_equity: float
    total_return_pct: float
    buy_hold_return_pct: float
    max_drawdown_pct: float
    num_trades: int
    win_rate_pct: float | None
    sharpe_ratio: float | None
    profit_factor: float | None
    avg_trade_pnl: float | None
    exposure_pct: float | None
    trades: list[Trade]
    equity_curve: pd.Series
    strategy_id: str = "sma_crossover"
    slippage_bps: float = 0.0
    commission_per_trade: float = 0.0
    commission_bps: float = 0.0
    total_commission: float = 0.0
    execution_mode: str = "next_open"


def _buy_qty(price: float, cash: float, max_notional: float, max_shares: int) -> int:
    if price <= 0:
        return 0
    by_notional = int(max_notional // price)
    by_cash = int(cash // price)
    qty = min(by_notional, by_cash, max_shares)
    return max(qty, 0)


def _round_trip_stats(trades: list[Trade]) -> tuple[float | None, float | None, float | None]:
    """Win rate %, profit factor, average PnL per round trip."""
    if not trades:
        return None, None, None

    wins = 0
    trips = 0
    gross_profit = 0.0
    gross_loss = 0.0
    pnls: list[float] = []
    entry_price: float | None = None
    entry_qty = 0

    for t in trades:
        if t.side == "buy":
            entry_price = t.price
            entry_qty = t.qty
        elif t.side == "sell" and entry_price is not None and entry_qty > 0:
            pnl = t.realized_pnl
            if pnl is None:
                pnl = (t.price - entry_price) * min(t.qty, entry_qty) - t.commission
            pnls.append(pnl)
            trips += 1
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)
            entry_price = None
            entry_qty = 0

    win_rate = (wins / trips * 100.0) if trips > 0 else None
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = None
    avg_pnl = sum(pnls) / len(pnls) if pnls else None
    return win_rate, profit_factor, avg_pnl


def _exposure_pct(trades: list[Trade], num_bars: int) -> float | None:
    if num_bars <= 0:
        return None
    if not trades:
        return 0.0
    held_days = 0
    last_buy: datetime | None = None
    first_ts = trades[0].timestamp
    last_ts = trades[-1].timestamp
    span_days = max((last_ts - first_ts).days, 1)
    for t in trades:
        if t.side == "buy":
            last_buy = t.timestamp
        elif t.side == "sell" and last_buy is not None:
            held_days += max((t.timestamp - last_buy).days, 1)
            last_buy = None
    return min(100.0, held_days / span_days * 100.0)


def build_backtest_result(
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    trades: list[Trade],
    equity_points: list[float],
    equity_index: list[datetime],
    strategy_id: str = "sma_crossover",
    fill_params: FillParams | None = None,
    total_commission: float = 0.0,
) -> BacktestResult:
    fp = fill_params or FillParams()
    equity_curve = pd.Series(
        equity_points, index=pd.DatetimeIndex(equity_index), name="equity"
    ).ffill()
    if equity_curve.isna().any():
        equity_curve = equity_curve.fillna(initial_cash)
    final_equity = float(equity_curve.iloc[-1])
    total_return_pct = (final_equity / initial_cash - 1.0) * 100.0

    closes = bars["close"].astype(float).dropna()
    first_close = float(closes.iloc[0])
    last_close = float(closes.iloc[-1])
    buy_hold_return_pct = (last_close / first_close - 1.0) * 100.0

    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    max_drawdown_pct = float(drawdown.min() * 100.0)

    win_rate_pct, profit_factor, avg_trade_pnl = _round_trip_stats(trades)
    exposure_pct = _exposure_pct(trades, len(bars))

    returns = equity_curve.pct_change().dropna()
    sharpe_ratio: float | None = None
    if len(returns) > 1 and returns.std() > 0:
        sharpe_ratio = float((returns.mean() / returns.std()) * (252**0.5))

    index = equity_curve.index
    start = index[0].to_pydatetime() if hasattr(index[0], "to_pydatetime") else index[0]
    end = index[-1].to_pydatetime() if hasattr(index[-1], "to_pydatetime") else index[-1]

    if profit_factor == float("inf"):
        profit_factor = None

    if total_commission == 0.0 and trades:
        total_commission = sum(t.commission for t in trades)

    return BacktestResult(
        symbol=symbol,
        start=start,
        end=end,
        initial_cash=initial_cash,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        buy_hold_return_pct=buy_hold_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        num_trades=len(trades),
        win_rate_pct=win_rate_pct,
        sharpe_ratio=sharpe_ratio,
        profit_factor=profit_factor,
        avg_trade_pnl=avg_trade_pnl,
        exposure_pct=exposure_pct,
        trades=trades,
        equity_curve=equity_curve,
        strategy_id=strategy_id,
        slippage_bps=fp.slippage_bps,
        commission_per_trade=fp.commission_per_trade,
        commission_bps=fp.commission_bps,
        total_commission=total_commission,
        execution_mode=fp.execution_mode,
    )


def run_backtest(
    bars: pd.DataFrame,
    *,
    symbol: str,
    fast_period: int,
    slow_period: int,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    fill_params: FillParams | None = None,
) -> BacktestResult:
    """Simulate SMA crossover on historical bars."""
    fp = fill_params or FillParams()
    if bars.empty:
        raise ValueError("bars must not be empty")

    bars = bars.sort_index()
    signals = sma_signal_series(bars, fast_period, slow_period)

    cash = float(initial_cash)
    shares = 0
    entry_price: float | None = None
    trades: list[Trade] = []
    equity_points: list[float] = []
    equity_index: list[datetime] = []
    total_commission = 0.0

    pending_signal: Signal | None = None
    bar_list = list(bars.iterrows())

    for i, (ts, row) in enumerate(bar_list):
        price = float(row["close"])

        if pending_signal is not None and shares <= 0 and pending_signal == Signal.BUY:
            use_open = fp.execution_mode == "next_open"
            base = float(row["open"]) if use_open else float(row["close"])
            qty = _buy_qty(base, cash, max_order_notional, max_position_shares)
            fill_price = apply_slippage(base, "buy", fp.slippage_bps)
            cost = qty * fill_price
            commission = calc_commission(
                cost,
                commission_per_trade=fp.commission_per_trade,
                commission_bps=fp.commission_bps,
            )
            if qty > 0 and cost + commission <= cash:
                cash -= cost + commission
                total_commission += commission
                shares += qty
                entry_price = fill_price
                trades.append(
                    Trade(
                        timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                        side="buy",
                        price=fill_price,
                        qty=qty,
                        cash_after=cash,
                        commission=commission,
                        slippage_bps=fp.slippage_bps,
                        execution_mode=fp.execution_mode,
                        reason="signal_entry",
                        position_after=shares,
                        equity_after=cash + shares * price,
                        strategy_id="sma_crossover",
                    )
                )
            pending_signal = None
        elif pending_signal == Signal.SELL and shares > 0:
            use_open = fp.execution_mode == "next_open"
            base = float(row["open"]) if use_open else float(row["close"])
            sell_qty = min(shares, max_position_shares)
            fill_price = apply_slippage(base, "sell", fp.slippage_bps)
            proceeds = sell_qty * fill_price
            commission = calc_commission(
                proceeds,
                commission_per_trade=fp.commission_per_trade,
                commission_bps=fp.commission_bps,
            )
            cash += proceeds - commission
            total_commission += commission
            shares -= sell_qty
            trades.append(
                Trade(
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    side="sell",
                    price=fill_price,
                    qty=sell_qty,
                    cash_after=cash,
                    commission=commission,
                    slippage_bps=fp.slippage_bps,
                    execution_mode=fp.execution_mode,
                    reason="signal_exit",
                    position_after=shares,
                    equity_after=cash + shares * price,
                    realized_pnl=(
                        (fill_price - entry_price) * sell_qty - commission
                        if entry_price
                        else None
                    ),
                    strategy_id="sma_crossover",
                )
            )
            entry_price = None
            pending_signal = None

        signal = Signal(signals.loc[ts])

        if fp.execution_mode == "same_close":
            if signal == Signal.BUY and shares <= 0:
                qty = _buy_qty(price, cash, max_order_notional, max_position_shares)
                fill_price = apply_slippage(price, "buy", fp.slippage_bps)
                cost = qty * fill_price
                commission = calc_commission(
                    cost,
                    commission_per_trade=fp.commission_per_trade,
                    commission_bps=fp.commission_bps,
                )
                if qty > 0 and cost + commission <= cash:
                    cash -= cost + commission
                    total_commission += commission
                    shares += qty
                    entry_price = fill_price
                    trades.append(
                        Trade(
                            timestamp=ts.to_pydatetime()
                            if hasattr(ts, "to_pydatetime")
                            else ts,
                            side="buy",
                            price=fill_price,
                            qty=qty,
                            cash_after=cash,
                            commission=commission,
                            slippage_bps=fp.slippage_bps,
                            execution_mode=fp.execution_mode,
                            reason="signal_entry",
                            position_after=shares,
                            equity_after=cash + shares * price,
                            strategy_id="sma_crossover",
                        )
                    )
            elif signal == Signal.SELL and shares > 0:
                sell_qty = min(shares, max_position_shares)
                fill_price = apply_slippage(price, "sell", fp.slippage_bps)
                proceeds = sell_qty * fill_price
                commission = calc_commission(
                    proceeds,
                    commission_per_trade=fp.commission_per_trade,
                    commission_bps=fp.commission_bps,
                )
                cash += proceeds - commission
                total_commission += commission
                shares -= sell_qty
                trades.append(
                    Trade(
                        timestamp=ts.to_pydatetime()
                        if hasattr(ts, "to_pydatetime")
                        else ts,
                        side="sell",
                        price=fill_price,
                        qty=sell_qty,
                        cash_after=cash,
                        commission=commission,
                        slippage_bps=fp.slippage_bps,
                        execution_mode=fp.execution_mode,
                        reason="signal_exit",
                        position_after=shares,
                        equity_after=cash + shares * price,
                        realized_pnl=(
                            (fill_price - entry_price) * sell_qty - commission
                            if entry_price
                            else None
                        ),
                        strategy_id="sma_crossover",
                    )
                )
                entry_price = None
        elif i < len(bar_list) - 1:
            if signal == Signal.BUY and shares <= 0:
                pending_signal = Signal.BUY
            elif signal == Signal.SELL and shares > 0:
                pending_signal = Signal.SELL

        equity_points.append(cash + shares * price)
        equity_index.append(
            ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        )

    return build_backtest_result(
        bars,
        symbol=symbol,
        initial_cash=initial_cash,
        trades=trades,
        equity_points=equity_points,
        equity_index=equity_index,
        strategy_id="sma_crossover",
        fill_params=fp,
        total_commission=total_commission,
    )
