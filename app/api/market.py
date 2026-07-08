"""Market data API: config, symbols, FX, live tick, chart bars, account."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.core.runtime import get_runtime
from app.services import backtest_service, market_data_service as mds

router = APIRouter()

_last_close_cache: dict[str, float] = {}


@router.get("/api/config")
def api_config() -> dict:
    rt = get_runtime()
    settings = rt.settings
    _, market, _ = mds.resolve_ticker(settings.symbol, settings)
    return {
        "symbol": settings.symbol,
        "market": market,
        "bar_timeframe": settings.bar_timeframe,
        "chart_refresh_seconds": settings.chart_refresh_seconds,
        "fast_sma_period": settings.fast_sma_period,
        "slow_sma_period": settings.slow_sma_period,
        "demo_mode": rt.demo_mode,
        "japan_stocks": mds.JAPAN_STOCKS,
        "us_stocks": mds.US_STOCKS,
        "display_currency": settings.display_currency,
        "backtest_initial_cash": settings.backtest_initial_cash,
        "backtest_initial_cash_jpy": backtest_service.resolve_initial_cash(
            settings, "jp", None
        ),
        "japan_backtest_note": "Japan backtests use Yahoo Finance (no Alpaca orders).",
    }


@router.get("/api/fx")
def api_fx() -> dict:
    settings = get_runtime().settings
    try:
        rate = mds.get_usdjpy_rate(settings.fx_usdjpy_manual)
    except Exception as exc:
        raise HTTPException(502, f"FX unavailable: {exc}") from exc
    return {"pair": "USDJPY", "rate": rate, "label": "JPY per 1 USD"}


@router.get("/api/stocks")
def api_stocks(market: str = Query("jp")) -> dict:
    if market == "us":
        return {"market": "us", "stocks": mds.US_STOCKS}
    return {"market": "jp", "stocks": mds.JAPAN_STOCKS}


@router.get("/api/tick")
def api_tick(
    symbol: str | None = Query(None),
    currency: str | None = Query(None, description="usd, jpy, or auto"),
    market: str | None = Query(None, description="us or jp"),
) -> dict:
    rt = get_runtime()
    settings = rt.settings
    demo_mode = rt.demo_mode
    raw = symbol or settings.symbol
    sym, mkt, alias_note = mds.resolve_ticker(raw, settings, market_hint=market)
    native, display, usdjpy, fx_failed = mds.currency_bundle(
        settings, raw, currency, market_hint=market
    )
    if demo_mode:
        tick = mds.demo_tick(sym, settings, _last_close_cache.get(sym))
    else:
        try:
            broker = mds.AlpacaBroker(settings) if mkt == "us" else None
            tick = mds.fetch_latest_tick(
                settings, sym, broker=broker, market_hint=market
            )
        except Exception as exc:
            raise HTTPException(502, f"Failed to load tick: {exc}") from exc
    native_close = float(tick["bar"]["close"])
    converted = not fx_failed and display != native
    if converted:
        tick = mds.apply_currency_to_tick(
            tick, native=native, display=display, usdjpy=usdjpy
        )
    tick["input_symbol"] = raw.upper()
    tick["data_symbol"] = sym
    if alias_note:
        tick["symbol_alias_note"] = alias_note
    tick["conversion"] = mds.build_conversion_info(
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


@router.get("/api/chart")
def api_chart(
    symbol: str | None = Query(None),
    start: str | None = Query(None, description="YYYY-MM-DD"),
    end: str | None = Query(None, description="YYYY-MM-DD"),
    currency: str | None = Query(None, description="usd, jpy, or auto"),
    market: str | None = Query(None, description="us or jp"),
) -> dict:
    rt = get_runtime()
    settings = rt.settings
    demo_mode = rt.demo_mode
    raw = symbol or settings.symbol
    sym, mkt, alias_note = mds.resolve_ticker(raw, settings, market_hint=market)
    end_date = (
        date.fromisoformat(end) if end else backtest_service.default_backtest_range()[1]
    )
    start_date = (
        date.fromisoformat(start)
        if start
        else backtest_service.default_backtest_range()[0]
    )
    if start_date >= end_date:
        raise HTTPException(400, "start must be before end")

    if demo_mode:
        bars = mds.generate_demo_bars(sym, start_date, end_date)
    else:
        try:
            broker = mds.AlpacaBroker(settings) if mkt == "us" else None
            bars = mds.fetch_bars_between(
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

    payload = mds.build_chart_payload(bars, symbol=sym, settings=settings, market=mkt)
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
    native, display, usdjpy, fx_failed = mds.currency_bundle(
        settings, raw, currency, market_hint=market
    )
    native_close = float(payload["last"]["close"]) if payload.get("last") else None
    converted = not fx_failed and display != native
    if converted:
        payload = mds.apply_currency_to_chart_payload(
            payload, native=native, display=display, usdjpy=usdjpy
        )
    elif fx_failed and display != native:
        payload["currency_warning"] = (
            f"FX rate unavailable; showing {native.upper()} prices."
        )
    payload["conversion"] = mds.build_conversion_info(
        native=native,
        display=display,
        usdjpy=usdjpy,
        native_close=native_close,
        applied=converted,
    )
    if payload.get("last"):
        _last_close_cache[sym] = payload["last"]["close"]
    return payload


@router.get("/api/account")
def api_account(
    currency: str | None = Query(None, description="usd, jpy, or auto"),
    market: str | None = Query(None, description="us or jp"),
) -> dict:
    rt = get_runtime()
    settings = rt.settings
    demo_mode = rt.demo_mode
    display = mds.resolve_display_currency(
        currency,
        symbol=settings.symbol,
        market_hint=market,
        default_setting=settings.display_currency,
    )
    account_native = "usd"
    usdjpy = 1.0
    fx_failed = False
    if display != account_native:
        try:
            usdjpy = mds.get_usdjpy_rate(settings.fx_usdjpy_manual)
        except Exception:
            display = account_native
            fx_failed = True
    if demo_mode:
        cash = mds.convert_amount(
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
                "FX rate unavailable; showing USD." if fx_failed else None
            ),
        }
    broker = mds.AlpacaBroker(settings)
    try:
        summary = broker.get_account_summary()
        position_qty = broker.get_position_qty(settings.symbol)
        equity = mds.convert_amount(
            float(summary["equity"]),
            from_currency=account_native,
            to_currency=display,
            usdjpy=usdjpy,
        )
        cash = mds.convert_amount(
            float(summary["cash"]),
            from_currency=account_native,
            to_currency=display,
            usdjpy=usdjpy,
        )
        buying_power = mds.convert_amount(
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
                "FX rate unavailable; showing USD." if fx_failed else None
            ),
        }
    except Exception as exc:
        raise HTTPException(502, f"Failed to load account: {exc}") from exc
