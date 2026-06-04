from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from stock_auto_trader.backtest.run import (
    default_backtest_range,
    execute_backtest,
    execute_backtest_compare,
    execute_backtest_scan,
)
from stock_auto_trader.broker.alpaca import AlpacaBroker
from stock_auto_trader.config import load_settings
from stock_auto_trader.data.fetch import fetch_bars_between, resolve_ticker
from stock_auto_trader.engine import TradingEngine
from stock_auto_trader.strategy.sma_crossover import compute_sma_signal

app = typer.Typer(
    name="stock-trader",
    help="Alpaca auto-trader with SMA crossover strategy.",
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command("status")
def status(
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to .env"),
) -> None:
    """Show account, position, and latest SMA signal."""
    settings = load_settings(env_file)
    ticker, market, alias_note = resolve_ticker(settings.symbol, settings)
    broker = AlpacaBroker(settings)
    engine = TradingEngine(settings, broker)

    end = date.today()
    start = end - timedelta(days=settings.lookback_bars * 3)
    bars = fetch_bars_between(
        settings, ticker, start, end, broker=broker if market == "us" else None
    )
    signal = compute_sma_signal(
        bars, settings.fast_sma_period, settings.slow_sma_period
    )

    table = Table(title="Stock Auto Trader")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Market", "Japan (Yahoo)" if market == "jp" else "US (Alpaca)")
    table.add_row("Symbol", ticker)
    if alias_note:
        table.add_row("Note", alias_note)
    table.add_row("Trading mode", settings.trading_mode)
    if market == "us":
        table.add_row("Base URL", settings.base_url)
        table.add_row("Orders enabled", str(settings.orders_enabled))
        account = broker.get_account_summary()
        position_qty = broker.get_position_qty(ticker)
        table.add_row("Market open", str(broker.is_market_open()))
        table.add_row("Position qty", str(position_qty))
        for key, value in account.items():
            table.add_row(key, str(value))
    else:
        table.add_row("Auto-trading", "disabled (Japan is data/backtest only)")
    table.add_row("SMA signal", signal.value)
    table.add_row("Kill switch", str(engine.kill_switch_active()))
    console.print(table)


@app.command("run-once")
def run_once(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Evaluate strategy once and place orders if rules allow."""
    _setup_logging(verbose)
    settings = load_settings(env_file)
    broker = AlpacaBroker(settings)
    engine = TradingEngine(settings, broker)
    outcome = engine.run_once()
    console.print(outcome)


@app.command("run")
def run(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the trading loop until interrupted (Ctrl+C)."""
    _setup_logging(verbose)
    settings = load_settings(env_file)
    broker = AlpacaBroker(settings)
    engine = TradingEngine(settings, broker)

    console.print(
        f"Starting trader for {settings.symbol} "
        f"({settings.trading_mode}, poll={settings.poll_interval_seconds}s)"
    )
    if settings.is_live and not settings.orders_enabled:
        console.print(
            "[yellow]Live mode: orders are DRY RUN until LIVE_TRADING_CONFIRMED=yes[/yellow]"
        )
    try:
        engine.run_loop()
    except KeyboardInterrupt:
        console.print("Stopped.")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid date '{value}', use YYYY-MM-DD") from exc


def _format_money(amount: float, market: str) -> str:
    if market == "jp":
        return f"¥{amount:,.0f}"
    return f"${amount:,.2f}"


def _print_backtest_result(
    result, *, market: str = "us", show_trades: bool = True
) -> None:
    table = Table(title=f"Backtest: {result.symbol}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Period", f"{result.start.date()} → {result.end.date()}")
    table.add_row("Initial cash", _format_money(result.initial_cash, market))
    table.add_row("Final equity", _format_money(result.final_equity, market))
    table.add_row("Strategy return", f"{result.total_return_pct:+.2f}%")
    table.add_row("Buy & hold return", f"{result.buy_hold_return_pct:+.2f}%")
    table.add_row("Max drawdown", f"{result.max_drawdown_pct:.2f}%")
    table.add_row("Trades", str(result.num_trades))
    win = (
        f"{result.win_rate_pct:.1f}%"
        if result.win_rate_pct is not None
        else "n/a (no round trips)"
    )
    table.add_row("Win rate", win)
    sharpe = (
        f"{result.sharpe_ratio:.2f}"
        if result.sharpe_ratio is not None
        else "n/a"
    )
    table.add_row("Sharpe (ann.)", sharpe)
    console.print(table)

    if show_trades and result.trades:
        trades_table = Table(title="Trades")
        trades_table.add_column("Time")
        trades_table.add_column("Side")
        trades_table.add_column("Qty")
        trades_table.add_column("Price")
        trades_table.add_column("Cash after")
        for trade in result.trades:
            trades_table.add_row(
                str(trade.timestamp),
                trade.side,
                str(trade.qty),
                _format_money(trade.price, market),
                _format_money(trade.cash_after, market),
            )
        console.print(trades_table)


@app.command("backtest")
def backtest(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    start: str | None = typer.Option(
        None,
        "--start",
        help="Start date (YYYY-MM-DD). Default: 2 years before end.",
    ),
    end: str | None = typer.Option(
        None,
        "--end",
        help="End date (YYYY-MM-DD). Default: today.",
    ),
    symbol: str | None = typer.Option(None, "--symbol", help="Override SYMBOL from .env"),
    market: str | None = typer.Option(
        None,
        "--market",
        help="us or jp (default: MARKET from .env)",
    ),
    strategy: str = typer.Option(
        "sma_crossover",
        "--strategy",
        help="Strategy id (sma_crossover, ma_trend_20_50, rsi_mean_reversion, ...)",
    ),
    compare: bool = typer.Option(
        False,
        "--compare",
        help="Run all supported strategies on the same data",
    ),
    initial_cash: float | None = typer.Option(
        None,
        "--initial-cash",
        help="Starting cash (default: BACKTEST_INITIAL_CASH)",
    ),
    csv_path: Path | None = typer.Option(
        None,
        "--csv",
        help="Use a local CSV instead of API/Yahoo (columns: timestamp/date, OHLCV)",
    ),
    show_trades: bool = typer.Option(True, "--trades/--no-trades"),
) -> None:
    """Backtest the SMA crossover strategy on historical bars."""
    settings = load_settings(env_file)
    sym = symbol or settings.symbol
    default_start, default_end = default_backtest_range()
    end_date = _parse_date(end) if end else default_end
    start_date = _parse_date(start) if start else default_start
    if start_date >= end_date:
        raise typer.BadParameter("--start must be before --end")

    if market and market.strip().lower() not in {"us", "jp"}:
        raise typer.BadParameter('--market must be "us" or "jp"')

    try:
        if compare:
            results, _, mkt, _, errors = execute_backtest_compare(
                settings,
                symbol=sym,
                start=start_date,
                end=end_date,
                initial_cash=initial_cash,
                csv_path=csv_path,
                market_hint=market,
            )
            table = Table(title=f"Strategy comparison: {sym}")
            table.add_column("Strategy")
            table.add_column("Return %")
            table.add_column("Max DD %")
            table.add_column("Win %")
            table.add_column("Trades")
            for r in sorted(results, key=lambda x: x.total_return_pct, reverse=True):
                from stock_auto_trader.strategy.strategies import STRATEGIES

                name = STRATEGIES.get(r.strategy_id, r.strategy_id).name
                win = (
                    f"{r.win_rate_pct:.0f}"
                    if r.win_rate_pct is not None
                    else "n/a"
                )
                table.add_row(
                    name,
                    f"{r.total_return_pct:+.2f}",
                    f"{r.max_drawdown_pct:.2f}",
                    win,
                    str(r.num_trades),
                )
            console.print(table)
            for err in errors:
                console.print(f"[dim]{err['strategy_name']}: {err['error']}[/dim]")
            return

        result, _, mkt, _ = execute_backtest(
            settings,
            symbol=sym,
            start=start_date,
            end=end_date,
            initial_cash=initial_cash,
            csv_path=csv_path,
            market_hint=market,
            strategy_id=strategy,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    from stock_auto_trader.strategy.strategies import STRATEGIES

    spec = STRATEGIES.get(result.strategy_id)
    if spec:
        console.print(f"[dim]{spec.name}: {spec.description}[/dim]")
    _print_backtest_result(result, market=mkt, show_trades=show_trades)
    if not show_trades and result.trades:
        console.print(f"[dim]{result.num_trades} trades (use --trades to list)[/dim]")


@app.command("backtest-scan")
def backtest_scan(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    symbols: str = typer.Option(
        ...,
        "--symbols",
        help="Comma-separated tickers (e.g. 6758.T,7203.T,SPY)",
    ),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    initial_cash: float | None = typer.Option(None, "--initial-cash"),
) -> None:
    """Compare all strategies across multiple symbols."""
    settings = load_settings(env_file)
    default_start, default_end = default_backtest_range()
    end_date = _parse_date(end) if end else default_end
    start_date = _parse_date(start) if start else default_start
    if start_date >= end_date:
        raise typer.BadParameter("--start must be before --end")

    tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not tickers:
        raise typer.BadParameter("Provide at least one symbol in --symbols")

    rows = execute_backtest_scan(
        settings,
        symbols=tickers,
        start=start_date,
        end=end_date,
        initial_cash=initial_cash,
    )

    table = Table(title=f"Backtest scan ({start_date} → {end_date})")
    table.add_column("Symbol")
    table.add_column("Strategy")
    table.add_column("Return %")
    table.add_column("B&H %")
    table.add_column("Max DD %")
    table.add_column("Trades")
    for row in rows:
        if row.get("error"):
            table.add_row(row.get("symbol", "?"), "—", "—", "—", "—", row["error"][:40])
            continue
        star = " *" if row.get("is_best_for_symbol") else ""
        table.add_row(
            row["data_symbol"],
            row["strategy_name"] + star,
            f"{row['total_return_pct']:+.2f}",
            f"{row['buy_hold_return_pct']:+.2f}",
            f"{row['max_drawdown_pct']:.2f}",
            str(row["num_trades"]),
        )
    console.print(table)
    console.print("[dim]* = best strategy for that symbol[/dim]")


@app.command("chart")
def chart(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Open a TradingView-style chart UI in your browser."""
    from stock_auto_trader.chart.server import run_server

    url = f"http://{host}:{port}/"
    console.print(f"[green]Chart server[/green] {url}")
    console.print(f"[green]Backtest page[/green] http://{host}:{port}/backtest")
    if not Path(env_file).exists():
        console.print(
            "[yellow]No .env with Alpaca keys — running in demo mode "
            "(synthetic data).[/yellow]"
        )
    console.print("Press Ctrl+C to stop.")
    try:
        run_server(host=host, port=port, env_path=env_file)
    except KeyboardInterrupt:
        console.print("Stopped.")


@app.command("kill-switch")
def kill_switch(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    enable: bool = typer.Option(
        True,
        "--enable/--disable",
        help="Create or remove the kill switch file",
    ),
) -> None:
    """Stop new orders by creating/removing .kill_switch."""
    settings = load_settings(env_file)
    path = settings.kill_switch_path
    if enable:
        path.touch()
        console.print(f"Kill switch ON: {path}")
    elif path.exists():
        path.unlink()
        console.print(f"Kill switch OFF: removed {path}")
    else:
        console.print("Kill switch already off.")


if __name__ == "__main__":
    app()
