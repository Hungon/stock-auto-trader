"""AI Opportunity Perspective service (scaffold).

The deterministic engine produces the score and setup type; this service turns
that into a natural-language "perspective" (summary, drivers, risks, what to
watch). In this build it uses a deterministic TEMPLATE generator (no LLM, no
secret). The private/pro build swaps in a real LLM provider while keeping this
template as the guaranteed fallback.

Principle: the AI layer only EXPLAINS; it never changes the score or gives
buy/sell advice. Every response carries a not-financial-advice disclaimer.
"""

from __future__ import annotations

from datetime import date

from app.backtest.run import default_backtest_range
from app.core.config import Settings
from app.data.fetch import resolve_ticker
from app.opportunity.engine import OpportunitySignal, compute_opportunity_signal
from app.opportunity.scan import _load_bars

DISCLAIMER = "Educational only — not financial advice."

__all__ = ["DISCLAIMER", "build_template_perspective", "generate_perspective"]


def _signal_alignment(sig: OpportunitySignal) -> str:
    mom, tech = sig.momentum_score, sig.technical_score
    if (mom >= 60 and tech >= 60) or (mom <= 40 and tech <= 40):
        return "aligned"
    if (mom >= 60 and tech <= 40) or (mom <= 40 and tech >= 60):
        return "conflicting"
    return "mixed"


def _summary(sig: OpportunitySignal) -> str:
    band = (
        "a strong" if sig.opportunity_score >= 65
        else "a developing" if sig.opportunity_score >= 50
        else "a weak"
    )
    return (
        f"{sig.symbol} is showing {band} setup classified as "
        f"'{sig.opportunity_type}' (score {sig.opportunity_score}/100). "
        f"Signals look {_signal_alignment(sig)} across momentum and trend."
    )


def _risk_factors(sig: OpportunitySignal) -> list[str]:
    risks: list[str] = []
    if sig.sma50 is not None and sig.price < sig.sma50:
        risks.append("Price is below the 50-day moving average (trend not confirmed).")
    if sig.rsi is not None and sig.rsi > 70:
        risks.append("RSI is elevated; momentum may be overextended.")
    if sig.rsi is not None and sig.rsi < 30:
        risks.append("RSI is very low; catching a falling knife is a risk.")
    if sig.volume_ratio is not None and sig.volume_ratio < 1.0:
        risks.append("Volume is below average, so the move lacks confirmation.")
    if sig.dist_from_high20_pct is not None and sig.dist_from_high20_pct < -10:
        risks.append("Price is well below its recent 20-day high.")
    if not risks:
        risks.append("No single dominant risk flag; treat as a normal-risk setup.")
    return risks


def build_template_perspective(sig: OpportunitySignal) -> dict:
    return {
        "symbol": sig.symbol,
        "market": sig.market,
        "opportunity_type": sig.opportunity_type,
        "opportunity_score": sig.opportunity_score,
        "confidence": sig.confidence,
        "source": "template",
        "model": None,
        "cached": False,
        "summary": _summary(sig),
        "signal_alignment": _signal_alignment(sig),
        "key_drivers": list(sig.explanation),
        "risk_factors": _risk_factors(sig),
        "watch_next": list(sig.watch_next),
        "disclaimer": DISCLAIMER,
    }


def generate_perspective(
    settings: Settings,
    *,
    market: str,
    symbol: str,
    name: str | None = None,
    start: date | None = None,
    end: date | None = None,
    demo_mode: bool = False,
) -> dict:
    """Recompute the signal server-side and return a template perspective."""
    market = (market or "jp").strip().lower()
    if market not in {"jp", "us"}:
        market = "jp"
    default_start, default_end = default_backtest_range()
    start = start or default_start
    end = end or default_end

    resolved, mkt, _ = resolve_ticker(symbol, settings, market_hint=market)
    bars = _load_bars(settings, resolved, mkt, start, end, demo_mode=demo_mode)
    sig = compute_opportunity_signal(resolved, name or symbol, mkt, bars)
    return build_template_perspective(sig)
