from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from alpaca.trading.enums import OrderSide
from rich.console import Console

from app.broker.alpaca import AlpacaBroker
from app.core.config import Settings
from app.data.fetch import fetch_bars_between, resolve_ticker
from app.core.logging_config import log_event
from app.risk.gate import RiskGate
from app.strategy.sma_crossover import Signal, compute_sma_signal

logger = logging.getLogger(__name__)
console = Console()


class TradingEngine:
    """Live/paper SMA crossover loop with pre-order risk gating."""

    def __init__(self, settings: Settings, broker: AlpacaBroker) -> None:
        self.settings = settings
        self.broker = broker
        self.risk_gate = RiskGate(settings, broker)

    def kill_switch_active(self) -> bool:
        return self.risk_gate.kill_switch_active()

    def run_once(self) -> dict:
        """Evaluate signal once, run risk checks, and optionally submit orders."""
        symbol = self.settings.symbol
        _, market, _ = resolve_ticker(symbol, self.settings)

        if market == "jp":
            return {
                "action": "skipped",
                "reason": "japan_symbols_are_data_only",
                "symbol": symbol,
                "message": "Use chart/backtest for Japan; Alpaca orders are US-only.",
            }

        end = date.today()
        start = end - timedelta(days=self.settings.lookback_bars * 3)
        bars = fetch_bars_between(
            self.settings, symbol, start, end, broker=self.broker
        )

        risk = self.risk_gate.pre_order_check(symbol=symbol, bars=bars)
        if not risk.allowed:
            msg = f"Orders blocked: {', '.join(risk.reasons)}"
            console.print(f"[yellow]{msg}[/yellow]")
            return {
                "action": "skipped",
                "reason": risk.reasons[0] if risk.reasons else "risk_check_failed",
                "reasons": risk.reasons,
                "events": risk.events,
            }

        signal = compute_sma_signal(
            bars,
            self.settings.fast_sma_period,
            self.settings.slow_sma_period,
        )
        position_qty = self.broker.get_position_qty(symbol)
        last_close = float(bars["close"].iloc[-1])

        log_event(
            logger,
            "signal_generated",
            symbol=symbol,
            strategy="sma_crossover",
            signal=signal.value,
            reason="fast_sma_crossed"
            if signal != Signal.HOLD
            else "no_crossover",
        )

        result = {
            "symbol": symbol,
            "signal": signal.value,
            "position_qty": position_qty,
            "last_close": last_close,
            "action": "hold",
        }

        if signal == Signal.BUY and position_qty <= 0:
            qty = self._buy_quantity(last_close)
            if qty > 0:
                result.update(self._maybe_buy(symbol, qty, last_close, bars))
            else:
                result["action"] = "skipped"
                result["reason"] = "buy_qty_zero_after_risk_limits"

        elif signal == Signal.SELL and position_qty > 0:
            sell_qty = min(int(position_qty), self.settings.max_position_shares)
            result.update(self._maybe_sell(symbol, sell_qty, last_close, bars))

        return result

    def run_loop(self, iterations: int | None = None) -> None:
        """Poll run_once until interrupted or *iterations* ticks complete."""
        log_event(
            logger,
            "bot_started",
            symbol=self.settings.symbol,
            trading_mode=self.settings.trading_mode,
        )
        count = 0
        while iterations is None or count < iterations:
            try:
                outcome = self.run_once()
                console.print(f"[cyan]tick[/cyan] {outcome}")
            except Exception:
                logger.exception("Trading tick failed")
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(self.settings.poll_interval_seconds)

    def _buy_quantity(self, price: float) -> int:
        if price <= 0:
            return 0
        max_by_notional = int(self.settings.max_order_notional // price)
        qty = min(max_by_notional, self.settings.max_position_shares)
        return max(qty, 0)

    def _maybe_buy(
        self, symbol: str, qty: int, price: float, bars
    ) -> dict:
        if not self.settings.orders_enabled:
            return {
                "action": "dry_run_buy",
                "qty": qty,
                "reason": "live_trading_not_confirmed",
            }

        risk = self.risk_gate.pre_order_check(
            symbol=symbol,
            bars=bars,
            side=OrderSide.BUY,
            qty=qty,
            price=price,
        )
        if not risk.allowed:
            msg = f"BUY blocked: {', '.join(risk.reasons)}"
            console.print(f"[red]{msg}[/red]")
            return {
                "action": "blocked",
                "side": "buy",
                "qty": qty,
                "reasons": risk.reasons,
            }

        order_id = self.broker.submit_market_order(symbol, OrderSide.BUY, qty)
        log_event(
            logger,
            "order_submitted",
            symbol=symbol,
            side="buy",
            qty=qty,
            order_id=order_id,
        )
        return {"action": "buy", "qty": qty, "order_id": order_id}

    def _maybe_sell(
        self, symbol: str, qty: int, price: float, bars
    ) -> dict:
        if not self.settings.orders_enabled:
            return {
                "action": "dry_run_sell",
                "qty": qty,
                "reason": "live_trading_not_confirmed",
            }

        risk = self.risk_gate.pre_order_check(
            symbol=symbol,
            bars=bars,
            side=OrderSide.SELL,
            qty=qty,
            price=price,
        )
        if not risk.allowed:
            msg = f"SELL blocked: {', '.join(risk.reasons)}"
            console.print(f"[red]{msg}[/red]")
            return {
                "action": "blocked",
                "side": "sell",
                "qty": qty,
                "reasons": risk.reasons,
            }

        order_id = self.broker.submit_market_order(symbol, OrderSide.SELL, qty)
        log_event(
            logger,
            "order_submitted",
            symbol=symbol,
            side="sell",
            qty=qty,
            order_id=order_id,
        )
        return {"action": "sell", "qty": qty, "order_id": order_id}
