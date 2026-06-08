"""Portfolio peak-to-trough drawdown checks."""
from __future__ import annotations

from dataclasses import dataclass

from stock_auto_trader.config import Settings
from stock_auto_trader.risk.state import RiskState


@dataclass(frozen=True)
class DrawdownCheck:
    """Result of comparing drawdown from peak equity to MAX_PORTFOLIO_DRAWDOWN_PCT."""

    breached: bool
    drawdown_pct: float
    peak_equity: float
    current_equity: float
    reason: str = ""


def check_drawdown(
    settings: Settings,
    state: RiskState,
    current_equity: float,
) -> DrawdownCheck:
    """Return breach status; disabled when MAX_PORTFOLIO_DRAWDOWN_PCT is zero."""
    if settings.max_portfolio_drawdown_pct <= 0:
        return DrawdownCheck(
            breached=False,
            drawdown_pct=0.0,
            peak_equity=state.peak_equity,
            current_equity=current_equity,
        )

    peak = max(state.peak_equity, current_equity)
    if peak <= 0:
        return DrawdownCheck(
            breached=False,
            drawdown_pct=0.0,
            peak_equity=peak,
            current_equity=current_equity,
            reason="peak_equity_zero",
        )

    drawdown_pct = (peak - current_equity) / peak * 100.0
    breached = drawdown_pct > settings.max_portfolio_drawdown_pct
    reason = ""
    if breached:
        reason = (
            f"drawdown {drawdown_pct:.2f}% exceeds limit "
            f"{settings.max_portfolio_drawdown_pct:.2f}%"
        )

    return DrawdownCheck(
        breached=breached,
        drawdown_pct=drawdown_pct,
        peak_equity=peak,
        current_equity=current_equity,
        reason=reason,
    )
