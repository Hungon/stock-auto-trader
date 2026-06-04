from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from stock_auto_trader.backtest.engine import Trade, _buy_qty


@dataclass
class PositionState:
    entry_price: float
    entry_bar: int
    breakout_level: float | None = None
    highest_close_since_entry: float | None = None


def _to_dt(ts) -> datetime:
    return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts


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
) -> tuple[list[Trade], list[float], list[datetime]]:
    """
    Long-only simulator. Fills at bar close.
    entry_signal / exit_signal: bool Series aligned with bars index.
    """
    bars = bars.sort_index()
    entry_signal = entry_signal.reindex(bars.index).fillna(False)
    exit_signal = exit_signal.reindex(bars.index).fillna(False)

    cash = float(initial_cash)
    shares = 0
    position: PositionState | None = None
    trades: list[Trade] = []
    equity_points: list[float] = []
    equity_index: list[datetime] = []

    last_valid_price: float | None = None
    for i, (ts, row) in enumerate(bars.iterrows()):
        raw_close = row["close"]
        if pd.isna(raw_close) or float(raw_close) <= 0:
            if last_valid_price is None:
                continue
            price = last_valid_price
        else:
            price = float(raw_close)
            last_valid_price = price
        exited_this_bar = False

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

            if (
                signal_exit
                or stop_hit
                or trail_exit
                or profit_hit
                or hold_expired
                or breakout_exit
            ):
                sell_qty = min(shares, max_position_shares)
                cash += sell_qty * price
                shares -= sell_qty
                trades.append(
                    Trade(
                        timestamp=_to_dt(ts),
                        side="sell",
                        price=price,
                        qty=sell_qty,
                        cash_after=cash,
                    )
                )
                position = None
                exited_this_bar = True

        if not exited_this_bar and shares <= 0 and bool(entry_signal.loc[ts]):
            qty = _buy_qty(price, cash, max_order_notional, max_position_shares)
            cost = qty * price
            if qty > 0 and cost <= cash:
                cash -= cost
                shares += qty
                breakout_level = None
                if track_breakout_level is not None:
                    raw = track_breakout_level.loc[ts]
                    if pd.notna(raw):
                        breakout_level = float(raw)
                position = PositionState(
                    entry_price=price,
                    entry_bar=i,
                    breakout_level=breakout_level,
                    highest_close_since_entry=price,
                )
                trades.append(
                    Trade(
                        timestamp=_to_dt(ts),
                        side="buy",
                        price=price,
                        qty=qty,
                        cash_after=cash,
                    )
                )

        equity_points.append(cash + shares * price)
        equity_index.append(_to_dt(ts))

    return trades, equity_points, equity_index
