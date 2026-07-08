"""Scan a universe of symbols and rank them by opportunity score.

Bar loading mirrors the chart endpoint: Japan symbols use yfinance, US symbols
use Alpaca (or synthetic demo bars when the app is running without API keys).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.backtest.run import default_backtest_range
from app.chart.demo import generate_demo_bars
from app.core.config import Settings
from app.data.bars_util import sanitize_bars
from app.data.fetch import fetch_bars_between, resolve_ticker
from app.markets.symbols import JAPAN_STOCKS, US_STOCKS
from app.opportunity.engine import (
    SETUP_TYPES,
    compute_opportunity_signal,
    signal_to_dict,
)


def _universe(market: str) -> list[dict[str, str]]:
    return US_STOCKS if market == "us" else JAPAN_STOCKS


def _load_bars(
    settings: Settings,
    symbol: str,
    market: str,
    start: date,
    end: date,
    *,
    demo_mode: bool,
) -> pd.DataFrame:
    if demo_mode and market == "us":
        bars = generate_demo_bars(symbol, start, end)
    else:
        bars = fetch_bars_between(
            settings, symbol, start, end, market_hint=market
        )
    return sanitize_bars(bars)


def _build_summary(signals: list[dict]) -> dict:
    if not signals:
        return {
            "market_bias": "No data",
            "breakout_count": 0,
            "high_volume_count": 0,
            "bearish_count": 0,
            "top_opportunity": None,
            "count": 0,
        }

    breakout_count = sum(
        1 for s in signals if s["opportunity_type"] == "Momentum Breakout"
    )
    bearish_count = sum(
        1 for s in signals if s["opportunity_type"] == "Bearish Breakdown"
    )
    high_volume_count = sum(
        1
        for s in signals
        if s["volume_ratio"] is not None and s["volume_ratio"] >= 2.0
    )

    avg_momentum = sum(s["momentum_score"] for s in signals) / len(signals)
    if avg_momentum >= 58.0:
        bias = "Bullish"
    elif avg_momentum <= 42.0:
        bias = "Bearish"
    else:
        bias = "Neutral"

    top = max(signals, key=lambda s: s["opportunity_score"])
    return {
        "market_bias": bias,
        "avg_momentum": round(avg_momentum, 1),
        "breakout_count": breakout_count,
        "high_volume_count": high_volume_count,
        "bearish_count": bearish_count,
        "top_opportunity": {
            "symbol": top["symbol"],
            "name": top["name"],
            "opportunity_score": top["opportunity_score"],
            "opportunity_type": top["opportunity_type"],
        },
        "count": len(signals),
    }


def scan_opportunities(
    settings: Settings,
    *,
    market: str = "jp",
    symbols: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    demo_mode: bool = False,
) -> dict:
    """Scan a market universe and return ranked opportunity signals + summary."""
    market = (market or "jp").strip().lower()
    if market not in {"jp", "us"}:
        market = "jp"

    default_start, default_end = default_backtest_range()
    start = start or default_start
    end = end or default_end

    if symbols:
        entries = [{"symbol": s.strip().upper(), "name": ""} for s in symbols if s.strip()]
    else:
        entries = _universe(market)

    signals: list[dict] = []
    errors: list[dict] = []
    for entry in entries:
        symbol = entry["symbol"]
        name = entry.get("name") or symbol
        try:
            resolved, mkt, _ = resolve_ticker(symbol, settings, market_hint=market)
            bars = _load_bars(
                settings, resolved, mkt, start, end, demo_mode=demo_mode
            )
            sig = compute_opportunity_signal(resolved, name, mkt, bars)
            row = signal_to_dict(sig)
            row["input_symbol"] = symbol
            signals.append(row)
        except Exception as exc:  # per-symbol failures should not abort the scan
            errors.append({"symbol": symbol, "name": name, "error": str(exc)})

    signals.sort(key=lambda s: s["opportunity_score"], reverse=True)
    for i, s in enumerate(signals, start=1):
        s["rank"] = i

    return {
        "market": market,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "setup_types": SETUP_TYPES,
        "summary": _build_summary(signals),
        "signals": signals,
        "errors": errors,
    }
