from __future__ import annotations

from datetime import datetime, timezone

from stock_auto_trader.config import Settings


def demo_tick(symbol: str, settings: Settings, last_close: float | None) -> dict:
    import random

    base = last_close if last_close else 400.0
    delta = random.uniform(-0.5, 0.5)
    price = round(base + delta, 2)
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%Y-%m-%d")
    return {
        "symbol": symbol,
        "time": time_str,
        "bar": {
            "time": time_str,
            "open": price,
            "high": price + 0.2,
            "low": price - 0.2,
            "close": price,
            "volume": 1_000_000,
        },
        "quote": {
            "bid": price - 0.01,
            "ask": price + 0.01,
            "bid_size": 100,
            "ask_size": 100,
        },
        "fetched_at": now.isoformat(),
        "demo_mode": True,
    }
