from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from pathlib import Path

from alpaca.trading.enums import OrderSide
from rich.console import Console

from stock_auto_trader.broker.alpaca import AlpacaBroker
from stock_auto_trader.config import Settings
from stock_auto_trader.data.fetch import fetch_bars_between, resolve_ticker
from stock_auto_trader.strategy.sma_crossover import Signal, compute_sma_signal

logger = logging.getLogger(__name__)
console = Console()


class TradingEngine:
    def __init__(self, settings: Settings, broker: AlpacaBroker) -> None:
        self.settings = settings
        self.broker = broker

    def kill_switch_active(self) -> bool:
        path: Path = self.settings.kill_switch_path
        return path.exists()

    def run_once(self) -> dict:
        symbol = self.settings.symbol
        _, market, _ = resolve_ticker(symbol, self.settings)

        if market == "jp":
            return {
                "action": "skipped",
                "reason": "japan_symbols_are_data_only",
                "symbol": symbol,
                "message": "Use chart/backtest for Japan; Alpaca orders are US-only.",
            }

        if self.kill_switch_active():
            return {"action": "skipped", "reason": "kill_switch_active"}

        if not self.broker.is_market_open():
            return {"action": "skipped", "reason": "market_closed"}

        end = date.today()
        start = end - timedelta(days=self.settings.lookback_bars * 3)
        bars = fetch_bars_between(
            self.settings, symbol, start, end, broker=self.broker
        )
        signal = compute_sma_signal(
            bars,
            self.settings.fast_sma_period,
            self.settings.slow_sma_period,
        )
        position_qty = self.broker.get_position_qty(symbol)
        last_close = float(bars["close"].iloc[-1])

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
                result.update(self._maybe_buy(symbol, qty))
            else:
                result["action"] = "skipped"
                result["reason"] = "buy_qty_zero_after_risk_limits"

        elif signal == Signal.SELL and position_qty > 0:
            sell_qty = min(int(position_qty), self.settings.max_position_shares)
            result.update(self._maybe_sell(symbol, sell_qty))

        return result

    def run_loop(self, iterations: int | None = None) -> None:
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

    def _maybe_buy(self, symbol: str, qty: int) -> dict:
        if not self.settings.orders_enabled:
            return {
                "action": "dry_run_buy",
                "qty": qty,
                "reason": "live_trading_not_confirmed",
            }
        order_id = self.broker.submit_market_order(symbol, OrderSide.BUY, qty)
        return {"action": "buy", "qty": qty, "order_id": order_id}

    def _maybe_sell(self, symbol: str, qty: int) -> dict:
        if not self.settings.orders_enabled:
            return {
                "action": "dry_run_sell",
                "qty": qty,
                "reason": "live_trading_not_confirmed",
            }
        order_id = self.broker.submit_market_order(symbol, OrderSide.SELL, qty)
        return {"action": "sell", "qty": qty, "order_id": order_id}
