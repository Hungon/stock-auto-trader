"""Export backtest trades to CSV or JSON trade journals."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import TextIO

from app.backtest.engine import BacktestResult, Trade

# Standard columns for ``stock-trader export-trades`` CSV output.
JOURNAL_COLUMNS = [
    "timestamp",
    "symbol",
    "market",
    "strategy",
    "side",
    "quantity",
    "price",
    "notional",
    "commission",
    "slippage_bps",
    "execution_mode",
    "reason",
    "cash_after",
    "position_after",
    "equity_after",
    "realized_pnl",
]


def trade_to_journal_row(trade: Trade, *, symbol: str, market: str) -> dict:
    """Map a :class:`Trade` to a flat dict suitable for CSV/JSON export."""
    return {
        "timestamp": trade.timestamp.isoformat(),
        "symbol": symbol,
        "market": market,
        "strategy": trade.strategy_id,
        "side": trade.side,
        "quantity": trade.qty,
        "price": trade.price,
        "notional": trade.notional,
        "commission": trade.commission,
        "slippage_bps": trade.slippage_bps,
        "execution_mode": trade.execution_mode,
        "reason": trade.reason,
        "cash_after": trade.cash_after,
        "position_after": trade.position_after,
        "equity_after": trade.equity_after,
        "realized_pnl": trade.realized_pnl,
    }


def export_trades_csv(
    trades: list[Trade],
    *,
    symbol: str,
    market: str = "us",
    output: TextIO | None = None,
) -> str:
    """Write trades as CSV to *output* or stdout."""
    out = output or sys.stdout
    writer = csv.DictWriter(out, fieldnames=JOURNAL_COLUMNS)
    writer.writeheader()
    for trade in trades:
        writer.writerow(trade_to_journal_row(trade, symbol=symbol, market=market))
    if isinstance(out, StringIO):
        return out.getvalue()
    return ""


def export_trades_json(
    trades: list[Trade],
    *,
    symbol: str,
    market: str = "us",
    output: TextIO | None = None,
) -> str:
    """Write trades as a JSON array to *output* or stdout."""
    rows = [trade_to_journal_row(t, symbol=symbol, market=market) for t in trades]
    payload = json.dumps(rows, indent=2, default=str)
    out = output or sys.stdout
    out.write(payload + "\n")
    return payload


def export_backtest_result(
    result: BacktestResult,
    *,
    market: str = "us",
    fmt: str = "csv",
    output_path: Path | None = None,
) -> None:
    """Write trades from a backtest result to *output_path* or stdout."""
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            if fmt == "json":
                export_trades_json(
                    result.trades, symbol=result.symbol, market=market, output=f
                )
            else:
                export_trades_csv(
                    result.trades, symbol=result.symbol, market=market, output=f
                )
    else:
        if fmt == "json":
            export_trades_json(result.trades, symbol=result.symbol, market=market)
        else:
            export_trades_csv(result.trades, symbol=result.symbol, market=market)


def load_trades_from_backtest_json(path: Path) -> tuple[list[dict], str, str]:
    """Parse trades from a backtest API/JSON payload."""
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "trades" in data:
        return (
            data["trades"],
            data.get("data_symbol", data.get("symbol", "")),
            data.get("market", "us"),
        )
    if isinstance(data, list):
        return data, "", "us"
    raise ValueError("Unsupported backtest JSON format")


def export_from_backtest_json(
    path: Path,
    *,
    fmt: str = "csv",
    output_path: Path | None = None,
) -> None:
    """Load trades from a saved backtest JSON file and export them."""
    rows, symbol, market = load_trades_from_backtest_json(path)
    trades = [
        Trade(
            timestamp=datetime.fromisoformat(str(r.get("time", r.get("timestamp")))),
            side=str(r["side"]),
            price=float(r["price"]),
            qty=int(r.get("qty", r.get("quantity", 0))),
            cash_after=float(r.get("cash_after", 0)),
            commission=float(r.get("commission", 0)),
            slippage_bps=float(r.get("slippage_bps", 0)),
            execution_mode=str(r.get("execution_mode", "")),
            reason=str(r.get("reason", "")),
            position_after=int(r.get("position_after", 0)),
            equity_after=float(r.get("equity_after", 0)),
            realized_pnl=(
                float(r["realized_pnl"]) if r.get("realized_pnl") is not None else None
            ),
            strategy_id=str(r.get("strategy", r.get("strategy_id", ""))),
            market=market,
        )
        for r in rows
    ]
    export_backtest_result(
        BacktestResult(
            symbol=symbol or "UNKNOWN",
            start=datetime.min,
            end=datetime.min,
            initial_cash=0,
            final_equity=0,
            total_return_pct=0,
            buy_hold_return_pct=0,
            max_drawdown_pct=0,
            num_trades=len(trades),
            win_rate_pct=None,
            sharpe_ratio=None,
            profit_factor=None,
            avg_trade_pnl=None,
            exposure_pct=None,
            trades=trades,
            equity_curve=__import__("pandas").Series(dtype=float),
        ),
        market=market,
        fmt=fmt,
        output_path=output_path,
    )
