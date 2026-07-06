"""Deterministic opportunity scoring and classification.

The engine takes an OHLCV DataFrame (same shape the backtester uses) and produces
a single `OpportunitySignal` describing the latest bar: sub-scores, a blended
opportunity score, a classified setup type, plain-language explanations, and a
rough fit against the existing backtest strategies.

No AI and no network here — everything is a pure function of the price/volume
history, which keeps the scanner reproducible and unit-testable.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import pandas as pd

from stock_auto_trader.strategy.indicators import (
    average_volume,
    highest_high,
    rsi,
    sma,
)

# Blend weights for the headline opportunity score (must sum to 1.0).
_WEIGHTS = {
    "momentum": 0.35,
    "volume": 0.25,
    "technical": 0.25,
    "setup": 0.15,
}

# Base setup-quality score per classified opportunity type.
_SETUP_BASE = {
    "Momentum Breakout": 85.0,
    "Pullback Setup": 70.0,
    "High Volume Alert": 65.0,
    "Oversold Rebound Watch": 60.0,
    "Neutral / Mixed": 45.0,
    "Bearish Breakdown": 20.0,
}


@dataclass
class OpportunitySignal:
    symbol: str
    name: str
    market: str
    price: float
    price_change_pct: float
    volume_ratio: float | None
    rsi: float | None
    sma20: float | None
    sma50: float | None
    sma200: float | None
    dist_from_high20_pct: float | None
    dist_from_low20_pct: float | None
    momentum_score: float
    volume_score: float
    technical_score: float
    setup_score: float
    opportunity_score: float
    opportunity_type: str
    confidence: str
    explanation: list[str] = field(default_factory=list)
    watch_next: list[str] = field(default_factory=list)
    strategy_fit: list[dict] = field(default_factory=list)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _f(value) -> float | None:
    """Coerce to a JSON-safe float, mapping NaN/inf to None."""
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    return num


def _last(series: pd.Series):
    if series is None or len(series) == 0:
        return None
    return _f(series.iloc[-1])


def _momentum_score(
    price_change_pct: float,
    close: float,
    sma20: float | None,
    sma50: float | None,
) -> float:
    score = 50.0
    score += _clamp(price_change_pct * 3.0, -15.0, 15.0)
    if sma20 is not None:
        score += 20.0 if close > sma20 else -20.0
    if sma20 is not None and sma50 is not None:
        score += 15.0 if sma20 > sma50 else -15.0
    return round(_clamp(score, 0.0, 100.0), 1)


def _volume_score(volume_ratio: float | None) -> float:
    if volume_ratio is None:
        return 50.0
    return round(_clamp(50.0 + (volume_ratio - 1.0) * 40.0, 0.0, 100.0), 1)


def _technical_score(
    close: float,
    sma20: float | None,
    sma50: float | None,
    sma200: float | None,
    rsi_val: float | None,
    dist_from_high20_pct: float | None,
) -> float:
    score = 50.0
    if sma20 is not None and sma50 is not None:
        if close > sma20 > sma50:
            score += 15.0
        elif close < sma20 < sma50:
            score -= 15.0
    if sma200 is not None:
        score += 10.0 if close > sma200 else -10.0
    if rsi_val is not None:
        if 55.0 <= rsi_val <= 70.0:
            score += 10.0
        elif rsi_val > 75.0:
            score -= 5.0
        elif rsi_val < 35.0:
            score += 5.0
    if dist_from_high20_pct is not None and dist_from_high20_pct > -2.0:
        score += 10.0
    return round(_clamp(score, 0.0, 100.0), 1)


def _classify(
    close: float,
    prior_high20: float | None,
    low20: float | None,
    sma20: float | None,
    sma50: float | None,
    rsi_val: float | None,
    volume_ratio: float | None,
) -> str:
    vr = volume_ratio if volume_ratio is not None else 1.0

    if (
        low20 is not None
        and rsi_val is not None
        and close <= low20
        and vr > 1.5
        and rsi_val < 45.0
    ):
        return "Bearish Breakdown"

    if (
        prior_high20 is not None
        and sma20 is not None
        and rsi_val is not None
        and close > prior_high20
        and vr > 1.5
        and 55.0 <= rsi_val <= 85.0
        and close > sma20
    ):
        return "Momentum Breakout"

    if (
        rsi_val is not None
        and low20 is not None
        and rsi_val < 35.0
        and vr > 1.2
        and close <= low20 * 1.05
    ):
        return "Oversold Rebound Watch"

    if vr > 2.0:
        return "High Volume Alert"

    if (
        sma20 is not None
        and sma50 is not None
        and rsi_val is not None
        and close > sma50
        and abs(close / sma20 - 1.0) < 0.03
        and 40.0 <= rsi_val <= 55.0
    ):
        return "Pullback Setup"

    return "Neutral / Mixed"


def _confidence(
    opportunity_score: float,
    opportunity_type: str,
    sma50: float | None,
    rsi_val: float | None,
) -> str:
    if sma50 is None or rsi_val is None:
        return "low"
    if opportunity_score >= 65.0 or opportunity_type in {
        "Momentum Breakout",
        "Bearish Breakdown",
    }:
        return "high"
    if opportunity_score <= 35.0:
        return "medium"
    return "medium"


def _explanation(sig_ctx: dict) -> list[str]:
    out: list[str] = []
    change = sig_ctx["price_change_pct"]
    if change > 0.2:
        out.append("Price is moving higher in the selected timeframe.")
    elif change < -0.2:
        out.append("Price is weaker in the selected timeframe.")
    else:
        out.append("Price is roughly flat in the selected timeframe.")

    vr = sig_ctx["volume_ratio"]
    if vr is not None:
        if vr > 1.5:
            out.append("Volume is above average, showing increased market attention.")
        elif vr < 0.7:
            out.append("Volume is below average, so conviction looks light.")

    rsi_val = sig_ctx["rsi"]
    if rsi_val is not None:
        if rsi_val > 70.0:
            out.append("RSI is elevated, so momentum may be stretched.")
        elif rsi_val < 35.0:
            out.append("RSI is low, suggesting the stock may be oversold.")

    sma20 = sig_ctx["sma20"]
    sma50 = sig_ctx["sma50"]
    close = sig_ctx["price"]
    if sma20 is not None and sma50 is not None:
        if sma20 > sma50:
            out.append("SMA20 is above SMA50, supporting a positive short-term trend.")
        else:
            out.append("SMA20 is below SMA50, indicating short-term weakness.")
    if sma20 is not None:
        if close < sma20:
            out.append("Price is trading below its 20-day moving average.")
    return out


def _watch_next(sig_ctx: dict) -> list[str]:
    out: list[str] = []
    close = sig_ctx["price"]
    sma20 = sig_ctx["sma20"]
    rsi_val = sig_ctx["rsi"]
    if sma20 is not None and close < sma20:
        out.append("Price reclaiming SMA20")
    if rsi_val is not None and rsi_val < 50.0:
        out.append("RSI recovering above 50")
    out.append("Volume rising above 1.5x average")
    dist_high = sig_ctx["dist_from_high20_pct"]
    if dist_high is not None and dist_high < 0:
        out.append("A close above the recent 20-day high")
    return out


def _strategy_fit(sig_ctx: dict, opportunity_type: str) -> list[dict]:
    close = sig_ctx["price"]
    sma20 = sig_ctx["sma20"]
    sma50 = sig_ctx["sma50"]
    sma200 = sig_ctx["sma200"]
    rsi_val = sig_ctx["rsi"]
    vr = sig_ctx["volume_ratio"] or 1.0

    uptrend = (
        sma20 is not None
        and sma50 is not None
        and close > sma20 > sma50
        and (sma200 is None or close > sma200)
    )
    above_sma50 = sma50 is not None and close > sma50

    def rank(strong: bool, possible: bool) -> str:
        if strong:
            return "strong"
        if possible:
            return "possible"
        return "weak"

    fits = [
        {
            "strategy_id": "breakout_20",
            "name": "Breakout (20-day high)",
            "fit": rank(
                opportunity_type == "Momentum Breakout",
                above_sma50 and vr > 1.2,
            ),
        },
        {
            "strategy_id": "rsi_mean_reversion",
            "name": "RSI Mean Reversion",
            "fit": rank(
                opportunity_type == "Oversold Rebound Watch",
                rsi_val is not None and rsi_val < 40.0,
            ),
        },
        {
            "strategy_id": "ma_trend_20_50",
            "name": "MA Trend 20/50",
            "fit": rank(uptrend, above_sma50),
        },
        {
            "strategy_id": "trend_risk_control",
            "name": "Trend + Risk Control",
            "fit": rank(
                uptrend and rsi_val is not None and 45.0 <= rsi_val <= 68.0,
                above_sma50,
            ),
        },
    ]
    return fits


def compute_opportunity_signal(
    symbol: str,
    name: str,
    market: str,
    bars: pd.DataFrame,
) -> OpportunitySignal:
    """Compute an OpportunitySignal from an OHLCV DataFrame.

    `bars` must have columns open, high, low, close, volume and be sorted by time.
    Indicators that need more history than is available resolve to None and are
    handled gracefully by scoring/classification.
    """
    if bars is None or bars.empty:
        raise ValueError("No bars provided")

    b = bars.sort_index()
    close_series = b["close"].astype(float)
    high_series = b["high"].astype(float)
    low_series = b["low"].astype(float)
    vol_series = b["volume"].astype(float)

    close = _f(close_series.iloc[-1])
    if close is None:
        raise ValueError("Latest close is not a valid number")

    prev_close = _f(close_series.iloc[-2]) if len(close_series) >= 2 else None
    price_change_pct = (
        (close / prev_close - 1.0) * 100.0
        if prev_close not in (None, 0.0)
        else 0.0
    )

    sma20 = _last(sma(close_series, 20))
    sma50 = _last(sma(close_series, 50))
    sma200 = _last(sma(close_series, 200))
    rsi_val = _last(rsi(close_series, 14))

    vol = _f(vol_series.iloc[-1])
    vol_avg20 = _last(average_volume(vol_series, 20))
    volume_ratio = (
        vol / vol_avg20 if (vol is not None and vol_avg20 not in (None, 0.0)) else None
    )

    high20_series = highest_high(high_series, 20)
    high20 = _last(high20_series)
    prior_high20 = (
        _f(high20_series.iloc[-2]) if len(high20_series) >= 2 else None
    )
    low20 = _last(low_series.rolling(20).min())

    dist_from_high20_pct = (
        (close / high20 - 1.0) * 100.0 if high20 not in (None, 0.0) else None
    )
    dist_from_low20_pct = (
        (close / low20 - 1.0) * 100.0 if low20 not in (None, 0.0) else None
    )

    momentum_score = _momentum_score(price_change_pct, close, sma20, sma50)
    volume_score = _volume_score(volume_ratio)
    technical_score = _technical_score(
        close, sma20, sma50, sma200, rsi_val, dist_from_high20_pct
    )
    opportunity_type = _classify(
        close, prior_high20, low20, sma20, sma50, rsi_val, volume_ratio
    )
    setup_score = _SETUP_BASE.get(opportunity_type, 45.0)

    opportunity_score = round(
        momentum_score * _WEIGHTS["momentum"]
        + volume_score * _WEIGHTS["volume"]
        + technical_score * _WEIGHTS["technical"]
        + setup_score * _WEIGHTS["setup"],
        1,
    )

    sig_ctx = {
        "price": close,
        "price_change_pct": price_change_pct,
        "volume_ratio": volume_ratio,
        "rsi": rsi_val,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "dist_from_high20_pct": dist_from_high20_pct,
    }

    return OpportunitySignal(
        symbol=symbol,
        name=name,
        market=market,
        price=round(close, 4),
        price_change_pct=round(price_change_pct, 2),
        volume_ratio=round(volume_ratio, 2) if volume_ratio is not None else None,
        rsi=round(rsi_val, 1) if rsi_val is not None else None,
        sma20=round(sma20, 4) if sma20 is not None else None,
        sma50=round(sma50, 4) if sma50 is not None else None,
        sma200=round(sma200, 4) if sma200 is not None else None,
        dist_from_high20_pct=(
            round(dist_from_high20_pct, 2)
            if dist_from_high20_pct is not None
            else None
        ),
        dist_from_low20_pct=(
            round(dist_from_low20_pct, 2)
            if dist_from_low20_pct is not None
            else None
        ),
        momentum_score=momentum_score,
        volume_score=volume_score,
        technical_score=technical_score,
        setup_score=setup_score,
        opportunity_score=opportunity_score,
        opportunity_type=opportunity_type,
        confidence=_confidence(opportunity_score, opportunity_type, sma50, rsi_val),
        explanation=_explanation(sig_ctx),
        watch_next=_watch_next(sig_ctx),
        strategy_fit=_strategy_fit(sig_ctx, opportunity_type),
    )


def signal_to_dict(sig: OpportunitySignal) -> dict:
    return asdict(sig)
