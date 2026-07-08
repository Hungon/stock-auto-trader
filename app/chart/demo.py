from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from alpaca.data.enums import DataFeed

from app.core.config import Settings


def demo_settings() -> Settings:
    return Settings(
        api_key="demo",
        secret_key="demo",
        base_url="https://paper-api.alpaca.markets",
        trading_mode="paper",
        live_trading_confirmed=False,
        symbol="SPY",
        fast_sma_period=10,
        slow_sma_period=30,
        bar_timeframe="1Day",
        lookback_bars=500,
        max_order_notional=500.0,
        max_position_shares=10,
        poll_interval_seconds=60,
        kill_switch_path=Path(".kill_switch"),
        backtest_initial_cash=10_000.0,
        backtest_initial_cash_jpy=1_000_000.0,
        backtest_max_order_notional_jpy=500_000.0,
        data_feed=DataFeed.IEX,
        chart_refresh_seconds=15,
        market="jp",
        display_currency="auto",
        fx_usdjpy_manual=None,
    )


def generate_demo_bars(
    symbol: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Synthetic daily OHLCV for chart preview without Alpaca keys."""
    idx = pd.bdate_range(start, end, tz="UTC")
    if len(idx) < 40:
        idx = pd.bdate_range(end - pd.Timedelta(days=120), end, tz="UTC")

    n = len(idx)
    rng = np.random.default_rng(abs(hash(symbol)) % (2**32))
    returns = rng.normal(0.0004, 0.012, n)
    close = 400 * np.cumprod(1 + returns)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    spread = rng.uniform(0.002, 0.01, n)
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = rng.integers(50_000_000, 150_000_000, n)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume.astype(float),
        },
        index=idx,
    )
