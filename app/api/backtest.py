"""Backtest API: strategy list, single/compare run, and multi-symbol scan."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.core.runtime import get_runtime
from app.services import backtest_service as bts
from app.services import market_data_service as mds

router = APIRouter()


def _backtest_currency_bundle(settings, raw, market, currency):
    ticker, _, _ = mds.resolve_ticker(raw, settings, market_hint=market)
    native = mds.native_currency_for_symbol(ticker)
    display = mds.resolve_display_currency(
        currency,
        symbol=ticker,
        market_hint=market,
        default_setting=settings.display_currency,
    )
    fx_convert = display != native
    usdjpy = 1.0
    if fx_convert:
        usdjpy = mds.get_usdjpy_rate(settings.fx_usdjpy_manual)
    return ticker, native, display, usdjpy, fx_convert


@router.get("/api/strategies")
def api_strategies() -> dict:
    return {"strategies": bts.list_strategies()}


@router.get("/api/backtest/scan")
def api_backtest_scan(
    symbols: str = Query(..., description="Comma-separated tickers"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    initial_cash: float | None = Query(None),
) -> dict:
    settings = get_runtime().settings
    tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not tickers:
        raise HTTPException(400, "symbols required")
    end_date = date.fromisoformat(end) if end else bts.default_backtest_range()[1]
    start_date = date.fromisoformat(start) if start else bts.default_backtest_range()[0]
    if start_date >= end_date:
        raise HTTPException(400, "start must be before end")
    try:
        rows = bts.execute_backtest_scan(
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


@router.get("/api/backtest")
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
    rt = get_runtime()
    settings = rt.settings
    demo_mode = rt.demo_mode
    raw = symbol or settings.symbol
    end_date = date.fromisoformat(end) if end else bts.default_backtest_range()[1]
    start_date = date.fromisoformat(start) if start else bts.default_backtest_range()[0]
    if start_date >= end_date:
        raise HTTPException(400, "start must be before end")

    _, mkt_preview, _ = mds.resolve_ticker(raw, settings, market_hint=market)
    if demo_mode and mkt_preview == "us":
        raise HTTPException(
            400,
            "US backtest requires Alpaca API keys in .env. "
            "For Japan, select Japan (TSE) and a .T symbol (e.g. 6758.T).",
        )

    try:
        _, _, display, usdjpy, fx_convert = _backtest_currency_bundle(
            settings, raw, market, currency
        )
    except Exception as exc:
        raise HTTPException(502, f"FX unavailable: {exc}") from exc

    try:
        if compare:
            results, sym, mkt, alias_note, errors = bts.execute_backtest_compare(
                settings,
                symbol=raw,
                start=start_date,
                end=end_date,
                initial_cash=initial_cash,
                market_hint=market,
            )
            rows = [
                bts.result_to_dict(
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

        result, sym, mkt, alias_note = bts.execute_backtest(
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

    return bts.result_to_dict(
        result,
        input_symbol=raw,
        data_symbol=sym,
        market=mkt,
        alias_note=alias_note,
        display_currency=display,
        usdjpy=usdjpy,
        fx_convert=fx_convert,
    )
