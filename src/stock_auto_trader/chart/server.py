from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from stock_auto_trader.broker.alpaca import AlpacaBroker
from stock_auto_trader.chart.currency_apply import (
    apply_currency_to_chart_payload,
    apply_currency_to_tick,
)
from stock_auto_trader.chart.demo import demo_settings, generate_demo_bars
from stock_auto_trader.chart.live import demo_tick
from stock_auto_trader.backtest.market_params import resolve_initial_cash
from stock_auto_trader.backtest.run import (
    default_backtest_range,
    execute_backtest,
    execute_backtest_compare,
    execute_backtest_scan,
)
from stock_auto_trader.strategy.strategies import list_strategies
from stock_auto_trader.backtest.serialize import result_to_dict
from stock_auto_trader.chart.series import build_chart_payload
from stock_auto_trader.config import Settings, load_settings
from stock_auto_trader.currency import (
    build_conversion_info,
    convert_amount,
    get_usdjpy_rate,
    native_currency_for_symbol,
    resolve_display_currency,
)
from stock_auto_trader.data.fetch import fetch_bars_between, fetch_latest_tick, resolve_ticker
from stock_auto_trader.markets.symbols import JAPAN_STOCKS, US_STOCKS
from stock_auto_trader.opportunity.scan import scan_opportunities

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = PROJECT_ROOT / "web" / "static"

_app: FastAPI | None = None
_settings: Settings | None = None
_last_close_cache: dict[str, float] = {}


def _currency_bundle(
    settings: Settings,
    symbol: str,
    currency: str | None,
    market_hint: str | None = None,
) -> tuple[str, str, float, bool]:
    """Return (native, display, usdjpy, fx_failed)."""
    ticker, _, _ = resolve_ticker(symbol, settings, market_hint=market_hint)
    native = native_currency_for_symbol(ticker)
    display = resolve_display_currency(
        currency,
        symbol=ticker,
        market_hint=market_hint,
        default_setting=settings.display_currency,
    )
    if display == native:
        return native, display, 1.0, False
    try:
        usdjpy = get_usdjpy_rate(settings.fx_usdjpy_manual)
        return native, display, usdjpy, False
    except Exception:
        return native, native, 1.0, True


def _resolve_settings(env_path: Path | None) -> tuple[Settings, bool]:
    try:
        return load_settings(env_path), False
    except ValueError:
        return demo_settings(), True


def create_app(env_path: Path | None = None) -> FastAPI:
    global _app, _settings
    settings, demo_mode = _resolve_settings(env_path)
    _settings = settings

    app = FastAPI(title="Stock Auto Trader Chart", version="0.1.0")

    @app.get("/api/config")
    def api_config() -> dict:
        _, market, _ = resolve_ticker(settings.symbol, settings)
        return {
            "symbol": settings.symbol,
            "market": market,
            "bar_timeframe": settings.bar_timeframe,
            "chart_refresh_seconds": settings.chart_refresh_seconds,
            "fast_sma_period": settings.fast_sma_period,
            "slow_sma_period": settings.slow_sma_period,
            "demo_mode": demo_mode,
            "japan_stocks": JAPAN_STOCKS,
            "us_stocks": US_STOCKS,
            "display_currency": settings.display_currency,
            "backtest_initial_cash": settings.backtest_initial_cash,
            "backtest_initial_cash_jpy": resolve_initial_cash(
                settings, "jp", None
            ),
            "japan_backtest_note": "Japan backtests use Yahoo Finance (no Alpaca orders).",
        }

    @app.get("/api/fx")
    def api_fx() -> dict:
        try:
            rate = get_usdjpy_rate(settings.fx_usdjpy_manual)
        except Exception as exc:
            raise HTTPException(502, f"FX unavailable: {exc}") from exc
        return {"pair": "USDJPY", "rate": rate, "label": "JPY per 1 USD"}

    @app.get("/api/stocks")
    def api_stocks(market: str = Query("jp")) -> dict:
        if market == "us":
            return {"market": "us", "stocks": US_STOCKS}
        return {"market": "jp", "stocks": JAPAN_STOCKS}

    @app.get("/api/tick")
    def api_tick(
        symbol: str | None = Query(None),
        currency: str | None = Query(None, description="usd, jpy, or auto"),
        market: str | None = Query(None, description="us or jp"),
    ) -> dict:
        raw = symbol or settings.symbol
        sym, mkt, alias_note = resolve_ticker(raw, settings, market_hint=market)
        native, display, usdjpy, fx_failed = _currency_bundle(
            settings, raw, currency, market_hint=market
        )
        if demo_mode:
            tick = demo_tick(sym, settings, _last_close_cache.get(sym))
        else:
            try:
                broker = AlpacaBroker(settings) if mkt == "us" else None
                tick = fetch_latest_tick(
                    settings, sym, broker=broker, market_hint=market
                )
            except Exception as exc:
                raise HTTPException(502, f"Failed to load tick: {exc}") from exc
        native_close = float(tick["bar"]["close"])
        converted = not fx_failed and display != native
        if converted:
            tick = apply_currency_to_tick(
                tick, native=native, display=display, usdjpy=usdjpy
            )
        tick["input_symbol"] = raw.upper()
        tick["data_symbol"] = sym
        if alias_note:
            tick["symbol_alias_note"] = alias_note
        tick["conversion"] = build_conversion_info(
            native=native,
            display=display,
            usdjpy=usdjpy,
            native_close=native_close,
            applied=converted,
        )
        if fx_failed and display != native:
            tick["currency_warning"] = (
                f"FX rate unavailable; showing {native.upper()} prices."
            )
        _last_close_cache[sym] = tick["bar"]["close"]
        return tick

    @app.get("/api/chart")
    def api_chart(
        symbol: str | None = Query(None),
        start: str | None = Query(None, description="YYYY-MM-DD"),
        end: str | None = Query(None, description="YYYY-MM-DD"),
        currency: str | None = Query(None, description="usd, jpy, or auto"),
        market: str | None = Query(None, description="us or jp"),
    ) -> dict:
        raw = symbol or settings.symbol
        sym, mkt, alias_note = resolve_ticker(raw, settings, market_hint=market)
        end_date = (
            date.fromisoformat(end) if end else default_backtest_range()[1]
        )
        start_date = (
            date.fromisoformat(start) if start else default_backtest_range()[0]
        )
        if start_date >= end_date:
            raise HTTPException(400, "start must be before end")

        if demo_mode:
            bars = generate_demo_bars(sym, start_date, end_date)
        else:
            try:
                broker = AlpacaBroker(settings) if mkt == "us" else None
                bars = fetch_bars_between(
                    settings,
                    sym,
                    start_date,
                    end_date,
                    broker=broker,
                    market_hint=market,
                )
            except Exception as exc:
                raise HTTPException(502, f"Failed to load bars: {exc}") from exc

        if bars.empty:
            raise HTTPException(404, f"No data for {sym} in range")

        payload = build_chart_payload(bars, symbol=sym, settings=settings, market=mkt)
        payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
        payload["input_symbol"] = raw.upper()
        payload["data_symbol"] = sym
        payload["market"] = mkt
        if alias_note:
            payload["symbol_alias_note"] = alias_note
        if mkt == "jp":
            payload["data_source"] = "yahoo_finance"
            payload["trading_note"] = "Japan: chart & backtest only (no Alpaca orders)"
        if demo_mode:
            payload["demo_mode"] = True
        native, display, usdjpy, fx_failed = _currency_bundle(
            settings, raw, currency, market_hint=market
        )
        native_close = (
            float(payload["last"]["close"]) if payload.get("last") else None
        )
        converted = not fx_failed and display != native
        if converted:
            payload = apply_currency_to_chart_payload(
                payload, native=native, display=display, usdjpy=usdjpy
            )
        elif fx_failed and display != native:
            payload["currency_warning"] = (
                f"FX rate unavailable; showing {native.upper()} prices."
            )
        payload["conversion"] = build_conversion_info(
            native=native,
            display=display,
            usdjpy=usdjpy,
            native_close=native_close,
            applied=converted,
        )
        if payload.get("last"):
            _last_close_cache[sym] = payload["last"]["close"]
        return payload

    @app.get("/api/account")
    def api_account(
        currency: str | None = Query(None, description="usd, jpy, or auto"),
        market: str | None = Query(None, description="us or jp"),
    ) -> dict:
        display = resolve_display_currency(
            currency,
            symbol=settings.symbol,
            market_hint=market,
            default_setting=settings.display_currency,
        )
        account_native: str = "usd"
        usdjpy = 1.0
        fx_failed = False
        if display != account_native:
            try:
                usdjpy = get_usdjpy_rate(settings.fx_usdjpy_manual)
            except Exception:
                display = account_native
                fx_failed = True
        if demo_mode:
            cash = convert_amount(
                settings.backtest_initial_cash,
                from_currency=account_native,
                to_currency=display,
                usdjpy=usdjpy,
            )
            return {
                "symbol": settings.symbol,
                "trading_mode": "demo",
                "market_open": True,
                "position_qty": 0,
                "status": "ACTIVE",
                "equity": cash,
                "cash": cash,
                "buying_power": cash,
                "pattern_day_trader": False,
                "demo_mode": True,
                "display_currency": display,
                "fx_usdjpy": usdjpy,
                "currency_warning": (
                    "FX rate unavailable; showing USD."
                    if fx_failed
                    else None
                ),
            }
        broker = AlpacaBroker(settings)
        try:
            summary = broker.get_account_summary()
            position_qty = broker.get_position_qty(settings.symbol)
            equity = convert_amount(
                float(summary["equity"]),
                from_currency=account_native,
                to_currency=display,
                usdjpy=usdjpy,
            )
            cash = convert_amount(
                float(summary["cash"]),
                from_currency=account_native,
                to_currency=display,
                usdjpy=usdjpy,
            )
            buying_power = convert_amount(
                float(summary["buying_power"]),
                from_currency=account_native,
                to_currency=display,
                usdjpy=usdjpy,
            )
            return {
                "symbol": settings.symbol,
                "trading_mode": settings.trading_mode,
                "market_open": broker.is_market_open(),
                "position_qty": position_qty,
                "status": summary["status"],
                "equity": equity,
                "cash": cash,
                "buying_power": buying_power,
                "pattern_day_trader": summary["pattern_day_trader"],
                "display_currency": display,
                "fx_usdjpy": usdjpy,
                "currency_warning": (
                    "FX rate unavailable; showing USD."
                    if fx_failed
                    else None
                ),
            }
        except Exception as exc:
            raise HTTPException(502, f"Failed to load account: {exc}") from exc

    @app.get("/api/strategies")
    def api_strategies() -> dict:
        return {"strategies": list_strategies()}

    @app.get("/api/opportunities")
    def api_opportunities(
        market: str | None = Query(None, description="us or jp"),
        symbols: str | None = Query(
            None, description="Optional comma-separated tickers to scan"
        ),
        start: str | None = Query(None, description="YYYY-MM-DD"),
        end: str | None = Query(None, description="YYYY-MM-DD"),
    ) -> dict:
        mkt = (market or "jp").strip().lower()
        if mkt not in {"jp", "us"}:
            mkt = "jp"
        symbol_list = (
            [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
        )
        try:
            start_date = date.fromisoformat(start) if start else None
            end_date = date.fromisoformat(end) if end else None
        except ValueError as exc:
            raise HTTPException(400, f"Invalid date: {exc}") from exc
        if start_date and end_date and start_date >= end_date:
            raise HTTPException(400, "start must be before end")
        try:
            return scan_opportunities(
                settings,
                market=mkt,
                symbols=symbol_list,
                start=start_date,
                end=end_date,
                demo_mode=demo_mode,
            )
        except Exception as exc:
            raise HTTPException(502, f"Opportunity scan failed: {exc}") from exc

    @app.get("/api/backtest/scan")
    def api_backtest_scan(
        symbols: str = Query(..., description="Comma-separated tickers"),
        start: str | None = Query(None),
        end: str | None = Query(None),
        initial_cash: float | None = Query(None),
    ) -> dict:
        tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not tickers:
            raise HTTPException(400, "symbols required")
        end_date = (
            date.fromisoformat(end) if end else default_backtest_range()[1]
        )
        start_date = (
            date.fromisoformat(start) if start else default_backtest_range()[0]
        )
        if start_date >= end_date:
            raise HTTPException(400, "start must be before end")
        try:
            rows = execute_backtest_scan(
                settings,
                symbols=tickers,
                start=start_date,
                end=end_date,
                initial_cash=initial_cash,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"Scan failed: {exc}") from exc
        return {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "rows": rows,
        }

    def _backtest_currency_bundle(raw: str, market: str | None, currency: str | None):
        ticker, _, _ = resolve_ticker(raw, settings, market_hint=market)
        native = native_currency_for_symbol(ticker)
        display = resolve_display_currency(
            currency,
            symbol=ticker,
            market_hint=market,
            default_setting=settings.display_currency,
        )
        fx_convert = display != native
        usdjpy = 1.0
        if fx_convert:
            usdjpy = get_usdjpy_rate(settings.fx_usdjpy_manual)
        return ticker, native, display, usdjpy, fx_convert

    @app.get("/api/backtest")
    def api_backtest(
        symbol: str | None = Query(None),
        start: str | None = Query(None, description="YYYY-MM-DD"),
        end: str | None = Query(None, description="YYYY-MM-DD"),
        currency: str | None = Query(None, description="usd, jpy, or auto"),
        market: str | None = Query(None, description="us or jp"),
        initial_cash: float | None = Query(None),
        strategy: str = Query("sma_crossover", description="Strategy id"),
        compare: bool = Query(False, description="Run all supported strategies"),
    ) -> dict:
        raw = symbol or settings.symbol
        end_date = (
            date.fromisoformat(end) if end else default_backtest_range()[1]
        )
        start_date = (
            date.fromisoformat(start) if start else default_backtest_range()[0]
        )
        if start_date >= end_date:
            raise HTTPException(400, "start must be before end")

        _, mkt_preview, _ = resolve_ticker(raw, settings, market_hint=market)
        if demo_mode and mkt_preview == "us":
            raise HTTPException(
                400,
                "US backtest requires Alpaca API keys in .env. "
                "For Japan, select Japan (TSE) and a .T symbol (e.g. 6758.T).",
            )

        try:
            _, _, display, usdjpy, fx_convert = _backtest_currency_bundle(
                raw, market, currency
            )
        except Exception as exc:
            raise HTTPException(502, f"FX unavailable: {exc}") from exc

        try:
            if compare:
                results, sym, mkt, alias_note, errors = execute_backtest_compare(
                    settings,
                    symbol=raw,
                    start=start_date,
                    end=end_date,
                    initial_cash=initial_cash,
                    market_hint=market,
                )
                rows = [
                    result_to_dict(
                        r,
                        input_symbol=raw,
                        data_symbol=sym,
                        market=mkt,
                        alias_note=alias_note,
                        display_currency=display,
                        usdjpy=usdjpy,
                        fx_convert=fx_convert,
                    )
                    for r in results
                ]
                return {
                    "compare": True,
                    "input_symbol": raw.upper(),
                    "data_symbol": sym,
                    "market": mkt,
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "display_currency": display,
                    "buy_hold_return_pct": (
                        rows[0]["buy_hold_return_pct"] if rows else None
                    ),
                    "results": rows,
                    "errors": errors,
                }

            result, sym, mkt, alias_note = execute_backtest(
                settings,
                symbol=raw,
                start=start_date,
                end=end_date,
                initial_cash=initial_cash,
                market_hint=market,
                strategy_id=strategy,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"Backtest failed: {exc}") from exc

        return result_to_dict(
            result,
            input_symbol=raw,
            data_symbol=sym,
            market=mkt,
            alias_note=alias_note,
            display_currency=display,
            usdjpy=usdjpy,
            fx_convert=fx_convert,
        )

    @app.get("/")
    def index() -> FileResponse:
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            raise HTTPException(500, "Static UI missing; reinstall project.")
        return FileResponse(index_file)

    @app.get("/backtest")
    def backtest_page() -> FileResponse:
        page = STATIC_DIR / "backtest.html"
        if not page.exists():
            raise HTTPException(500, "Backtest UI missing; reinstall project.")
        return FileResponse(page)

    @app.get("/opportunity")
    def opportunity_page() -> FileResponse:
        page = STATIC_DIR / "opportunity.html"
        if not page.exists():
            raise HTTPException(500, "Opportunity UI missing; reinstall project.")
        return FileResponse(page)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    _app = app
    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    env_path: Path | None = None,
) -> None:
    import uvicorn

    app = create_app(env_path)
    uvicorn.run(app, host=host, port=port, log_level="info")
