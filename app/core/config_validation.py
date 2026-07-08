"""Startup validation for Settings loaded from the environment.

Fatal issues block CLI commands; warnings (e.g. live mode without confirmation)
are surfaced in ``stock-trader status`` but do not exit.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import LIVE_BASE_URL, PAPER_BASE_URL, Settings

EXECUTION_MODES = frozenset({"same_close", "next_open", "next_close"})
LOG_FORMATS = frozenset({"text", "json"})
RISK_ACTIONS = frozenset({"block_orders", "kill_switch", "liquidate"})


@dataclass(frozen=True)
class ValidationIssue:
    """Single config problem tied to an env var name."""

    field: str
    message: str
    fatal: bool = True


@dataclass(frozen=True)
class ValidationResult:
    """Aggregate validation outcome; ``valid`` is False when any fatal issue exists."""

    valid: bool
    issues: tuple[ValidationIssue, ...]

    @property
    def fatal_issues(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.fatal)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if not i.fatal)


def validate_settings(settings: Settings) -> ValidationResult:
    """Check trading, risk, backtest, and logging settings for safe values."""
    issues: list[ValidationIssue] = []

    if settings.trading_mode not in {"live", "paper"}:
        issues.append(
            ValidationIssue("TRADING_MODE", 'Must be "live" or "paper"')
        )

    if settings.is_live and not settings.live_trading_confirmed:
        issues.append(
            ValidationIssue(
                "LIVE_TRADING_CONFIRMED",
                'Live trading requires LIVE_TRADING_CONFIRMED=yes',
                fatal=False,
            )
        )

    if settings.is_live and settings.base_url == PAPER_BASE_URL:
        issues.append(
            ValidationIssue(
                "ALPACA_BASE_URL",
                f"Live mode must not use paper URL ({PAPER_BASE_URL})",
            )
        )

    if not settings.is_live and settings.base_url == LIVE_BASE_URL:
        issues.append(
            ValidationIssue(
                "ALPACA_BASE_URL",
                f"Paper mode is using live URL ({LIVE_BASE_URL})",
                fatal=False,
            )
        )

    if settings.fast_sma_period >= settings.slow_sma_period:
        issues.append(
            ValidationIssue(
                "FAST_SMA_PERIOD",
                "FAST_SMA_PERIOD must be less than SLOW_SMA_PERIOD",
            )
        )

    for name, value in [
        ("MAX_ORDER_NOTIONAL", settings.max_order_notional),
        ("MAX_DAILY_LOSS_USD", settings.max_daily_loss_usd),
        ("MAX_DAILY_LOSS_PCT", settings.max_daily_loss_pct),
        ("MAX_PORTFOLIO_DRAWDOWN_PCT", settings.max_portfolio_drawdown_pct),
        ("BACKTEST_SLIPPAGE_BPS", settings.backtest_slippage_bps),
        ("BACKTEST_COMMISSION_PER_TRADE", settings.backtest_commission_per_trade),
        ("BACKTEST_COMMISSION_BPS", settings.backtest_commission_bps),
    ]:
        if value < 0:
            issues.append(ValidationIssue(name, f"{name} must be non-negative"))

    if settings.backtest_execution_mode not in EXECUTION_MODES:
        issues.append(
            ValidationIssue(
                "BACKTEST_EXECUTION_MODE",
                f"Must be one of {sorted(EXECUTION_MODES)}",
            )
        )

    if settings.log_format not in LOG_FORMATS:
        issues.append(
            ValidationIssue(
                "LOG_FORMAT",
                f'Must be one of {sorted(LOG_FORMATS)}',
            )
        )

    if settings.daily_loss_action not in RISK_ACTIONS:
        issues.append(
            ValidationIssue(
                "DAILY_LOSS_ACTION",
                f"Must be one of {sorted(RISK_ACTIONS)}",
            )
        )

    if settings.drawdown_action not in RISK_ACTIONS:
        issues.append(
            ValidationIssue(
                "DRAWDOWN_ACTION",
                f"Must be one of {sorted(RISK_ACTIONS)}",
            )
        )

    if settings.no_trade_first_minutes < 0:
        issues.append(
            ValidationIssue("NO_TRADE_FIRST_MINUTES", "Must be non-negative")
        )
    if settings.no_trade_last_minutes < 0:
        issues.append(
            ValidationIssue("NO_TRADE_LAST_MINUTES", "Must be non-negative")
        )

    fatal = any(i.fatal for i in issues)
    return ValidationResult(valid=not fatal, issues=tuple(issues))
