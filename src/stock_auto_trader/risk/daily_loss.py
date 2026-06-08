"""Daily loss limit checks against starting equity for the current session."""
from __future__ import annotations

from dataclasses import dataclass

from stock_auto_trader.config import Settings
from stock_auto_trader.risk.state import RiskState, update_risk_state


@dataclass(frozen=True)
class DailyLossCheck:
    """Result of comparing today's loss to MAX_DAILY_LOSS_* limits."""

    breached: bool
    daily_loss_usd: float
    daily_loss_pct: float
    starting_equity: float
    current_equity: float
    reason: str = ""


def check_daily_loss(
    settings: Settings,
    state: RiskState,
    current_equity: float,
) -> DailyLossCheck:
    """Return breach status; disabled when both USD and pct limits are zero."""
    if settings.max_daily_loss_usd <= 0 and settings.max_daily_loss_pct <= 0:
        return DailyLossCheck(
            breached=False,
            daily_loss_usd=0.0,
            daily_loss_pct=0.0,
            starting_equity=state.starting_equity,
            current_equity=current_equity,
        )

    starting = state.starting_equity
    if starting <= 0:
        return DailyLossCheck(
            breached=False,
            daily_loss_usd=0.0,
            daily_loss_pct=0.0,
            starting_equity=starting,
            current_equity=current_equity,
            reason="starting_equity_zero",
        )

    daily_loss_usd = starting - current_equity
    daily_loss_pct = daily_loss_usd / starting * 100.0

    breached = False
    reasons: list[str] = []
    if settings.max_daily_loss_usd > 0 and daily_loss_usd > settings.max_daily_loss_usd:
        breached = True
        reasons.append(
            f"daily loss ${daily_loss_usd:.2f} exceeds limit ${settings.max_daily_loss_usd:.2f}"
        )
    if settings.max_daily_loss_pct > 0 and daily_loss_pct > settings.max_daily_loss_pct:
        breached = True
        reasons.append(
            f"daily loss {daily_loss_pct:.2f}% exceeds limit {settings.max_daily_loss_pct:.2f}%"
        )

    return DailyLossCheck(
        breached=breached,
        daily_loss_usd=daily_loss_usd,
        daily_loss_pct=daily_loss_pct,
        starting_equity=starting,
        current_equity=current_equity,
        reason="; ".join(reasons),
    )


def refresh_daily_state(settings: Settings, current_equity: float) -> RiskState:
    """Load, update, and persist risk state for the current trading day."""
    return update_risk_state(settings.risk_state_path, current_equity)
