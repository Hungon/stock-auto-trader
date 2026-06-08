from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from stock_auto_trader.backtest.engine import Trade, _buy_qty
from stock_auto_trader.backtest.execution import (
    FillParams,
    apply_slippage,
    calc_commission,
)


@dataclass
class PositionState:
    entry_price: float
    entry_bar: int
    breakout_level: float | None = None
    highest_close_since_entry: float | None = None


def _to_dt(ts) -> datetime:
    return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts


def _base_price(row, execution_mode: str, use_open: bool) -> float:
    if use_open and execution_mode == "next_open":
        return float(row["open"])
    return float(row["close"])


def simulate_long_only(
    bars: pd.DataFrame,
    *,
    symbol: str,
    initial_cash: float,
    max_order_notional: float,
    max_position_shares: int,
    entry_signal: pd.Series,
    exit_signal: pd.Series,
    stop_loss_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    max_hold_bars: int | None = None,
    take_profit_pct: float | None = None,
    min_hold_bars: int | None = None,
    track_breakout_level: pd.Series | None = None,
    fill_params: FillParams | None = None,
    strategy_id: str = "",
    market: str = "us",
) -> tuple[list[Trade], list[float], list[datetime], float]:
    """
    Long-only simulator with configurable execution timing, slippage, and commission.

    Signal-based entries/exits defer one bar for next_open/next_close modes.
    Risk exits (stop/trail/take-profit) fill at the current bar close.
    Returns (trades, equity_points, equity_index, total_commission).
    """
    fp = fill_params or FillParams()
    bars = bars.sort_index()
    entry_signal = entry_signal.reindex(bars.index).fillna(False)
    exit_signal = exit_signal.reindex(bars.index).fillna(False)

    cash = float(initial_cash)
    shares = 0
    position: PositionState | None = None
    trades: list[Trade] = []
    equity_points: list[float] = []
    equity_index: list[datetime] = []
    total_commission = 0.0

    pending_entry = False
    pending_exit = False
    entry_ref_price: float | None = None
    entry_ref_qty = 0

    last_valid_price: float | None = None
    bar_list = list(bars.iterrows())

    for i, (ts, row) in enumerate(bar_list):
        raw_close = row["close"]
        if pd.isna(raw_close) or float(raw_close) <= 0:
            if last_valid_price is None:
                continue
            price = last_valid_price
        else:
            price = float(raw_close)
            last_valid_price = price
        exited_this_bar = False

        # Execute deferred signal orders at start of bar
        if pending_exit and shares > 0 and position is not None:
            use_open = fp.execution_mode == "next_open"
            base = _base_price(row, fp.execution_mode, use_open)
            sell_qty = min(shares, max_position_shares)
            cash += sell_qty * apply_slippage(base, "sell", fp.slippage_bps)
            notional = base * sell_qty
            commission = calc_commission(
                notional,
                commission_per_trade=fp.commission_per_trade,
                commission_bps=fp.commission_bps,
            )
            cash -= commission
            total_commission += commission
            shares -= sell_qty
            trades.append(
                Trade(
                    timestamp=_to_dt(ts),
                    side="sell",
                    price=apply_slippage(base, "sell", fp.slippage_bps),
                    qty=sell_qty,
                    cash_after=cash,
                    commission=commission,
                    slippage_bps=fp.slippage_bps,
                    execution_mode=fp.execution_mode,
                    reason="signal_exit",
                    position_after=shares,
                    equity_after=cash + shares * price,
                    realized_pnl=(
                        (apply_slippage(base, "sell", fp.slippage_bps) - entry_ref_price)
                        * min(sell_qty, entry_ref_qty)
                        - commission
                        if entry_ref_price
                        else None
                    ),
                    strategy_id=strategy_id,
                    market=market,
                )
            )
            position = None
            pending_exit = False
            exited_this_bar = True
            entry_ref_price = None
            entry_ref_qty = 0

        if pending_entry and shares <= 0 and not exited_this_bar:
            use_open = fp.execution_mode == "next_open"
            base = _base_price(row, fp.execution_mode, use_open)
            qty = _buy_qty(base, cash, max_order_notional, max_position_shares)
            fill_price = apply_slippage(base, "buy", fp.slippage_bps)
            cost = qty * fill_price
            commission = calc_commission(
                cost,
                commission_per_trade=fp.commission_per_trade,
                commission_bps=fp.commission_bps,
            )
            total_cost = cost + commission
            if qty > 0 and total_cost <= cash:
                cash -= total_cost
                total_commission += commission
                shares += qty
                breakout_level = None
                if track_breakout_level is not None:
                    raw = track_breakout_level.loc[ts]
                    if pd.notna(raw):
                        breakout_level = float(raw)
                position = PositionState(
                    entry_price=fill_price,
                    entry_bar=i,
                    breakout_level=breakout_level,
                    highest_close_since_entry=price,
                )
                entry_ref_price = fill_price
                entry_ref_qty = qty
                trades.append(
                    Trade(
                        timestamp=_to_dt(ts),
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
                        strategy_id=strategy_id,
                        market=market,
                    )
                )
            pending_entry = False

        if shares > 0 and position is not None:
            position.highest_close_since_entry = max(
                position.highest_close_since_entry or price, price
            )
            stop_hit = False
            if stop_loss_pct is not None:
                stop_hit = price <= position.entry_price * (1.0 - stop_loss_pct)
            trail_hit = False
            if trailing_stop_pct is not None and position.highest_close_since_entry:
                trail_hit = price <= position.highest_close_since_entry * (
                    1.0 - trailing_stop_pct
                )
            hold_expired = (
                max_hold_bars is not None
                and (i - position.entry_bar) >= max_hold_bars
            )
            profit_hit = False
            if take_profit_pct is not None:
                profit_hit = price >= position.entry_price * (1.0 + take_profit_pct)
            breakout_fail = False
            if track_breakout_level is not None and position.breakout_level is not None:
                level = float(track_breakout_level.loc[ts])
                if pd.notna(level):
                    breakout_fail = price < level

            bars_held = i - position.entry_bar
            can_soft_exit = min_hold_bars is None or bars_held >= min_hold_bars
            signal_exit = bool(exit_signal.loc[ts]) and can_soft_exit
            trail_exit = trail_hit and can_soft_exit
            breakout_exit = breakout_fail and can_soft_exit

            risk_exit = stop_hit or trail_exit or profit_hit or hold_expired or breakout_exit

            if risk_exit:
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
                        timestamp=_to_dt(ts),
                        side="sell",
                        price=fill_price,
                        qty=sell_qty,
                        cash_after=cash,
                        commission=commission,
                        slippage_bps=fp.slippage_bps,
                        execution_mode="same_close",
                        reason="risk_exit",
                        position_after=shares,
                        equity_after=cash + shares * price,
                        realized_pnl=(
                            (fill_price - position.entry_price) * sell_qty - commission
                        ),
                        strategy_id=strategy_id,
                        market=market,
                    )
                )
                position = None
                exited_this_bar = True
                entry_ref_price = None
                entry_ref_qty = 0
            elif signal_exit:
                if fp.execution_mode == "same_close":
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
                            timestamp=_to_dt(ts),
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
                                (fill_price - position.entry_price) * sell_qty - commission
                            ),
                            strategy_id=strategy_id,
                            market=market,
                        )
                    )
                    position = None
                    exited_this_bar = True
                    entry_ref_price = None
                    entry_ref_qty = 0
                elif i < len(bar_list) - 1:
                    pending_exit = True

        if (
            not exited_this_bar
            and shares <= 0
            and not pending_entry
            and bool(entry_signal.loc[ts])
        ):
            if fp.execution_mode == "same_close":
                qty = _buy_qty(price, cash, max_order_notional, max_position_shares)
                fill_price = apply_slippage(price, "buy", fp.slippage_bps)
                cost = qty * fill_price
                commission = calc_commission(
                    cost,
                    commission_per_trade=fp.commission_per_trade,
                    commission_bps=fp.commission_bps,
                )
                total_cost = cost + commission
                if qty > 0 and total_cost <= cash:
                    cash -= total_cost
                    total_commission += commission
                    shares += qty
                    breakout_level = None
                    if track_breakout_level is not None:
                        raw = track_breakout_level.loc[ts]
                        if pd.notna(raw):
                            breakout_level = float(raw)
                    position = PositionState(
                        entry_price=fill_price,
                        entry_bar=i,
                        breakout_level=breakout_level,
                        highest_close_since_entry=price,
                    )
                    entry_ref_price = fill_price
                    entry_ref_qty = qty
                    trades.append(
                        Trade(
                            timestamp=_to_dt(ts),
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
                            strategy_id=strategy_id,
                            market=market,
                        )
                    )
            elif i < len(bar_list) - 1:
                pending_entry = True

        equity_points.append(cash + shares * price)
        equity_index.append(_to_dt(ts))

    return trades, equity_points, equity_index, total_commission
