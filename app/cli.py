from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.backtest.run import (
    default_backtest_range,
    execute_backtest,
    execute_backtest_compare,
    execute_backtest_scan,
)
from app.backtest.walk_forward import run_walk_forward
from app.broker.alpaca import AlpacaBroker
from app.core.config import demo_build_enabled, load_settings
from app.core.config_validation import validate_settings
from app.data.fetch import fetch_bars_between, resolve_ticker
from app.engine import TradingEngine
from app.core.logging_config import log_event, setup_logging
from app.strategy.sma_crossover import compute_sma_signal
from app.trade_journal import export_backtest_result, export_from_backtest_json

app = typer.Typer(
    name="stock-trader",
    help="Alpaca auto-trader with SMA crossover strategy.",
)
console = Console()
logger = logging.getLogger(__name__)


def _load_and_validate(env_file: Path):
    """Load settings and exit the CLI if fatal validation errors exist."""
    settings = load_settings(env_file)
    validation = validate_settings(settings)
    if not validation.valid:
        for issue in validation.fatal_issues:
            console.print(f"[red]Config error ({issue.field}): {issue.message}[/red]")
            log_event(
                logger,
                "config_validation_failed",
                level=logging.ERROR,
                field=issue.field,
                message=issue.message,
            )
        raise typer.Exit(code=1)
    log_event(logger, "config_loaded", trading_mode=settings.trading_mode)
    return settings, validation


def _setup_logging(verbose: bool, settings) -> None:
    setup_logging(settings, verbose=verbose)


@app.command("status")
def status(
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to .env"),
) -> None:
    """Show account, position, and latest SMA signal."""
    settings, validation = _load_and_validate(env_file)
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
    if demo_build_enabled():
        table.add_row("Build", "DEMO (live/paper orders disabled)")
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
    if validation.warnings:
        for w in validation.warnings:
            table.add_row(f"Warning ({w.field})", w.message)
    else:
        table.add_row("Config validation", "OK")
    console.print(table)


@app.command("run-once")
def run_once(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Evaluate strategy once and place orders if rules allow."""
    settings, _ = _load_and_validate(env_file)
    _setup_logging(verbose, settings)
    if demo_build_enabled():
        console.print(
            "[yellow]DEMO build: signals are evaluated but no orders are submitted.[/yellow]"
        )
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
    settings, _ = _load_and_validate(env_file)
    _setup_logging(verbose, settings)
    broker = AlpacaBroker(settings)
    engine = TradingEngine(settings, broker)

    console.print(
        f"Starting trader for {settings.symbol} "
        f"({settings.trading_mode}, poll={settings.poll_interval_seconds}s)"
    )
    if demo_build_enabled():
        console.print(
            "[yellow]DEMO build: order submission is disabled; running signal-only "
            "(dry run). See the private 'pro' build for live trading.[/yellow]"
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
    table.add_row("Execution mode", result.execution_mode)
    table.add_row("Slippage (bps)", str(result.slippage_bps))
    table.add_row("Commission/trade", f"{result.commission_per_trade:.4f}")
    table.add_row("Commission (bps)", str(result.commission_bps))
    table.add_row("Total commission", f"{result.total_commission:.4f}")
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
    export_trades: Path | None = typer.Option(
        None,
        "--export-trades",
        help="Export trade journal to CSV or JSON (by extension)",
    ),
) -> None:
    """Backtest the SMA crossover strategy on historical bars."""
    settings, _ = _load_and_validate(env_file)
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
                from app.strategy.strategies import STRATEGIES

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
    from app.strategy.strategies import STRATEGIES

    spec = STRATEGIES.get(result.strategy_id)
    if spec:
        console.print(f"[dim]{spec.name}: {spec.description}[/dim]")
    _print_backtest_result(result, market=mkt, show_trades=show_trades)
    if export_trades:
        fmt = "json" if export_trades.suffix.lower() == ".json" else "csv"
        export_backtest_result(result, market=mkt, fmt=fmt, output_path=export_trades)
        console.print(f"[green]Trades exported to[/green] {export_trades}")
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
    settings, _ = _load_and_validate(env_file)
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
    from app.main import run_server

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
    settings, _ = _load_and_validate(env_file)
    path = settings.kill_switch_path
    if enable:
        path.touch()
        console.print(f"Kill switch ON: {path}")
    elif path.exists():
        path.unlink()
        console.print(f"Kill switch OFF: removed {path}")
    else:
        console.print("Kill switch already off.")


@app.command("export-trades")
def export_trades_cmd(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    input_file: Path | None = typer.Option(
        None,
        "--input",
        help="Backtest result JSON file",
    ),
    fmt: str = typer.Option("csv", "--format", help="csv or json"),
    output: Path | None = typer.Option(None, "--output", help="Output file (stdout if omitted)"),
    symbol: str | None = typer.Option(None, "--symbol"),
    strategy: str = typer.Option("sma_crossover", "--strategy"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
) -> None:
    """Export trade journal from backtest results."""
    if fmt not in {"csv", "json"}:
        raise typer.BadParameter('--format must be "csv" or "json"')

    if input_file:
        export_from_backtest_json(input_file, fmt=fmt, output_path=output)
        if output:
            console.print(f"[green]Exported to[/green] {output}")
        return

    settings, _ = _load_and_validate(env_file)
    sym = symbol or settings.symbol
    default_start, default_end = default_backtest_range()
    end_date = _parse_date(end) if end else default_end
    start_date = _parse_date(start) if start else default_start

    result, _, mkt, _ = execute_backtest(
        settings,
        symbol=sym,
        start=start_date,
        end=end_date,
        strategy_id=strategy,
    )
    export_backtest_result(result, market=mkt, fmt=fmt, output_path=output)
    if output:
        console.print(f"[green]Exported {result.num_trades} trades to[/green] {output}")


@app.command("walk-forward")
def walk_forward_cmd(
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    symbol: str = typer.Option("SPY", "--symbol"),
    strategy: str = typer.Option("sma_crossover", "--strategy"),
    start: str = typer.Option(..., "--start", help="YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="YYYY-MM-DD"),
    train_years: int = typer.Option(3, "--train-years"),
    test_months: int = typer.Option(6, "--test-months"),
    initial_cash: float | None = typer.Option(None, "--initial-cash"),
    compare: bool = typer.Option(
        False,
        "--compare",
        help="Compare all supported strategies (summary only)",
    ),
) -> None:
    """Run walk-forward out-of-sample backtests."""
    settings, _ = _load_and_validate(env_file)
    _setup_logging(False, settings)
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date >= end_date:
        raise typer.BadParameter("--start must be before --end")

    if compare:
        from app.strategy.strategies import STRATEGIES

        table = Table(title=f"Walk-forward compare: {symbol}")
        table.add_column("Strategy")
        table.add_column("Windows")
        table.add_column("Total return %")
        table.add_column("Max DD %")
        table.add_column("Trades")
        for spec in STRATEGIES.values():
            if not spec.supported:
                continue
            try:
                summary = run_walk_forward(
                    settings,
                    symbol=symbol,
                    strategy_id=spec.id,
                    start=start_date,
                    end=end_date,
                    train_years=train_years,
                    test_months=test_months,
                    initial_cash=initial_cash,
                )
                table.add_row(
                    spec.name,
                    str(summary.number_of_windows),
                    f"{summary.total_return_pct:+.2f}",
                    f"{summary.max_drawdown_pct:.2f}",
                    str(summary.total_trades),
                )
            except Exception as exc:
                table.add_row(spec.name, "—", "—", "—", str(exc)[:30])
        console.print(table)
        return

    summary = run_walk_forward(
        settings,
        symbol=symbol,
        strategy_id=strategy,
        start=start_date,
        end=end_date,
        train_years=train_years,
        test_months=test_months,
        initial_cash=initial_cash,
    )

    summary_table = Table(title=f"Walk-forward: {symbol} / {strategy}")
    summary_table.add_column("Metric")
    summary_table.add_column("Value")
    summary_table.add_row("Windows", str(summary.number_of_windows))
    summary_table.add_row("Total return", f"{summary.total_return_pct:+.2f}%")
    if summary.annualized_return_pct is not None:
        summary_table.add_row("CAGR (approx.)", f"{summary.annualized_return_pct:+.2f}%")
    summary_table.add_row("Max drawdown", f"{summary.max_drawdown_pct:.2f}%")
    if summary.sharpe_ratio is not None:
        summary_table.add_row("Sharpe (avg)", f"{summary.sharpe_ratio:.2f}")
    if summary.win_rate_pct is not None:
        summary_table.add_row("Win rate (avg)", f"{summary.win_rate_pct:.1f}%")
    if summary.profit_factor is not None:
        summary_table.add_row("Profit factor (avg)", f"{summary.profit_factor:.2f}")
    summary_table.add_row("Total trades", str(summary.total_trades))
    console.print(summary_table)

    window_table = Table(title="Per-window results")
    window_table.add_column("Window")
    window_table.add_column("Train start")
    window_table.add_column("Train end")
    window_table.add_column("Test start")
    window_table.add_column("Test end")
    window_table.add_column("Return %")
    window_table.add_column("Max DD %")
    window_table.add_column("Sharpe")
    window_table.add_column("Trades")
    for w in summary.windows:
        sharpe = (
            f"{w.result.sharpe_ratio:.2f}"
            if w.result.sharpe_ratio is not None
            else "n/a"
        )
        window_table.add_row(
            str(w.window),
            str(w.train_start),
            str(w.train_end),
            str(w.test_start),
            str(w.test_end),
            f"{w.result.total_return_pct:+.2f}",
            f"{w.result.max_drawdown_pct:.2f}",
            sharpe,
            str(w.result.num_trades),
        )
    console.print(window_table)


if __name__ == "__main__":
    app()
