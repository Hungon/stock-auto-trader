from __future__ import annotations

from app.backtest.engine import BacktestResult
from app.currency import (
    build_conversion_info,
    convert_amount,
    native_currency_for_market,
)
from app.strategy.strategies import STRATEGIES


def _bar_time(ts) -> str:
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%d")
    return str(ts)[:10]


def result_to_dict(
    result: BacktestResult,
    *,
    input_symbol: str,
    data_symbol: str,
    market: str,
    alias_note: str | None,
    display_currency: str | None = None,
    usdjpy: float = 1.0,
    fx_convert: bool = False,
) -> dict:
    native = native_currency_for_market(market)
    display = display_currency or native

    initial = result.initial_cash
    final = result.final_equity
    if fx_convert and display != native:
        initial = convert_amount(
            initial, from_currency=native, to_currency=display, usdjpy=usdjpy
        )
        final = convert_amount(
            final, from_currency=native, to_currency=display, usdjpy=usdjpy
        )

    equity = []
    for ts, value in result.equity_curve.items():
        if value is None or (isinstance(value, float) and value != value):
            continue
        v = float(value)
        if fx_convert and display != native:
            v = convert_amount(v, from_currency=native, to_currency=display, usdjpy=usdjpy)
        equity.append({"time": _bar_time(ts), "value": v})

    trades = []
    for t in result.trades:
        price = float(t.price)
        cash_after = float(t.cash_after)
        if fx_convert and display != native:
            price = convert_amount(
                price, from_currency=native, to_currency=display, usdjpy=usdjpy
            )
            cash_after = convert_amount(
                cash_after, from_currency=native, to_currency=display, usdjpy=usdjpy
            )
        trades.append(
            {
                "time": _bar_time(t.timestamp),
                "side": t.side,
                "qty": t.qty,
                "price": price,
                "cash_after": cash_after,
                "commission": t.commission,
                "slippage_bps": t.slippage_bps,
                "execution_mode": t.execution_mode,
                "reason": t.reason,
                "position_after": t.position_after,
                "equity_after": t.equity_after,
                "realized_pnl": t.realized_pnl,
            }
        )

    spec = STRATEGIES.get(result.strategy_id)
    strategy_name = spec.name if spec else result.strategy_id

    payload = {
        "input_symbol": input_symbol.upper(),
        "data_symbol": data_symbol,
        "market": market,
        "symbol_alias_note": alias_note,
        "strategy_id": result.strategy_id,
        "strategy_name": strategy_name,
        "start": _bar_time(result.start),
        "end": _bar_time(result.end),
        "initial_cash": initial,
        "final_equity": final,
        "total_return_pct": result.total_return_pct,
        "buy_hold_return_pct": result.buy_hold_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "num_trades": result.num_trades,
        "win_rate_pct": result.win_rate_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "profit_factor": result.profit_factor,
        "avg_trade_pnl": (
            convert_amount(
                result.avg_trade_pnl,
                from_currency=native,
                to_currency=display,
                usdjpy=usdjpy,
            )
            if fx_convert
            and display != native
            and result.avg_trade_pnl is not None
            else result.avg_trade_pnl
        ),
        "exposure_pct": result.exposure_pct,
        "slippage_bps": result.slippage_bps,
        "commission_per_trade": result.commission_per_trade,
        "commission_bps": result.commission_bps,
        "total_commission": result.total_commission,
        "execution_mode": result.execution_mode,
        "native_currency": native,
        "display_currency": display,
        "equity_curve": equity,
        "trades": trades,
        "conversion": build_conversion_info(
            native=native,
            display=display,
            usdjpy=usdjpy,
            native_close=result.final_equity,
            applied=fx_convert and display != native,
        ),
    }
    return payload
