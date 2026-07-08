"""Central pre-order risk gate for live and paper trading."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd
from alpaca.trading.enums import OrderSide

from app.broker.alpaca import AlpacaBroker
from app.core.config import Settings
from app.core.logging_config import log_event
from app.risk.daily_loss import check_daily_loss, refresh_daily_state
from app.risk.drawdown import check_drawdown
from app.risk.market_hours import evaluate_market_hours
from app.risk.stale_data import check_stale_data
from app.risk.state import save_risk_state

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    """Outcome of :meth:`RiskGate.pre_order_check`."""

    allowed: bool
    reasons: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


class RiskGate:
    """Run all configured risk checks before submitting orders to Alpaca."""

    def __init__(self, settings: Settings, broker: AlpacaBroker) -> None:
        self.settings = settings
        self.broker = broker

    def kill_switch_active(self) -> bool:
        return self.settings.kill_switch_path.exists()

    def enable_kill_switch(self) -> None:
        self.settings.kill_switch_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.kill_switch_path.touch()
        log_event(logger, "kill_switch_enabled", path=str(self.settings.kill_switch_path))

    def pre_order_check(
        self,
        *,
        symbol: str,
        bars: pd.DataFrame,
        side: OrderSide | None = None,
        qty: int = 0,
        price: float = 0.0,
    ) -> RiskCheckResult:
        """Return whether an order may proceed; blocks on first failed check."""
        result = RiskCheckResult(allowed=True)

        if self.kill_switch_active():
            result.allowed = False
            result.reasons.append("kill_switch_active")
            result.events.append("kill_switch_enabled")
            return result

        if not self.settings.orders_enabled and self.settings.is_live:
            result.allowed = False
            result.reasons.append("live_trading_not_confirmed")
            return result

        stale = check_stale_data(self.settings, symbol, bars)
        if stale.stale:
            result.allowed = False
            result.reasons.append(stale.reason or "stale_data")
            result.events.append("stale_data_detected")
            log_event(
                logger,
                "stale_data_detected",
                level=logging.WARNING,
                symbol=symbol,
                latest_bar_time=(
                    stale.latest_bar_time.isoformat() if stale.latest_bar_time else None
                ),
                now=stale.now.isoformat(),
                max_age_seconds=stale.max_age_seconds,
            )
            return result

        clock = self.broker.get_market_clock()
        hours = evaluate_market_hours(
            clock,
            require_market_open=self.settings.require_market_open,
            allow_premarket=self.settings.allow_premarket,
            allow_afterhours=self.settings.allow_afterhours,
            no_trade_first_minutes=self.settings.no_trade_first_minutes,
            no_trade_last_minutes=self.settings.no_trade_last_minutes,
        )
        if not hours.allowed:
            result.allowed = False
            result.reasons.append(hours.reason or "market_closed")
            result.events.append("market_closed_blocked_order")
            log_event(
                logger,
                "market_closed_blocked_order",
                level=logging.WARNING,
                symbol=symbol,
                reason=hours.reason,
            )
            return result

        try:
            account = self.broker.get_account_summary()
            current_equity = float(account["equity"])
        except Exception as exc:
            result.allowed = False
            result.reasons.append(f"account_fetch_failed: {exc}")
            return result

        state = refresh_daily_state(self.settings, current_equity)
        if current_equity > state.peak_equity:
            state.peak_equity = current_equity
            save_risk_state(self.settings.risk_state_path, state)

        daily = check_daily_loss(self.settings, state, current_equity)
        if daily.breached:
            result.allowed = False
            result.reasons.append(daily.reason)
            result.events.append("daily_loss_limit_breached")
            log_event(
                logger,
                "daily_loss_limit_breached",
                level=logging.ERROR,
                daily_loss_usd=daily.daily_loss_usd,
                daily_loss_pct=daily.daily_loss_pct,
                starting_equity=daily.starting_equity,
                current_equity=daily.current_equity,
            )
            self._apply_risk_action(
                result, self.settings.daily_loss_action, symbol=symbol
            )
            return result

        dd = check_drawdown(self.settings, state, current_equity)
        if dd.breached:
            result.allowed = False
            result.reasons.append(dd.reason)
            result.events.append("drawdown_limit_breached")
            log_event(
                logger,
                "drawdown_limit_breached",
                level=logging.ERROR,
                drawdown_pct=dd.drawdown_pct,
                peak_equity=dd.peak_equity,
                current_equity=dd.current_equity,
            )
            self._apply_risk_action(
                result, self.settings.drawdown_action, symbol=symbol
            )
            return result

        if side is not None and qty > 0 and price > 0:
            notional = qty * price
            if notional > self.settings.max_order_notional:
                result.allowed = False
                result.reasons.append(
                    f"order notional ${notional:.2f} exceeds "
                    f"MAX_ORDER_NOTIONAL ${self.settings.max_order_notional:.2f}"
                )
            if qty > self.settings.max_position_shares:
                result.allowed = False
                result.reasons.append(
                    f"qty {qty} exceeds MAX_POSITION_SHARES "
                    f"{self.settings.max_position_shares}"
                )

        if result.allowed:
            log_event(logger, "risk_check_passed", symbol=symbol)
        else:
            log_event(
                logger,
                "risk_check_failed",
                level=logging.WARNING,
                symbol=symbol,
                reasons=result.reasons,
            )

        return result

    def _apply_risk_action(
        self,
        result: RiskCheckResult,
        action: str,
        *,
        symbol: str,
    ) -> None:
        if action == "kill_switch":
            self.enable_kill_switch()
            result.actions.append("kill_switch_enabled")
        elif action == "liquidate":
            result.actions.append("liquidate_requested")
            try:
                self.broker.cancel_all_orders()
                self.broker.close_all_positions()
                result.actions.append("liquidated")
            except Exception as exc:
                result.reasons.append(f"liquidation_failed: {exc}")
                log_event(
                    logger,
                    "liquidation_failed",
                    level=logging.ERROR,
                    symbol=symbol,
                    error=str(exc),
                )
        else:
            result.actions.append("block_orders")
