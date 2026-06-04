from stock_auto_trader.backtest.market_params import (
    resolve_backtest_limits,
    resolve_initial_cash,
)
from stock_auto_trader.config import Settings
from alpaca.data.enums import DataFeed
from pathlib import Path


def _settings(**kwargs) -> Settings:
    base = dict(
        api_key="k",
        secret_key="s",
        base_url="https://paper-api.alpaca.markets",
        trading_mode="paper",
        live_trading_confirmed=False,
        symbol="SPY",
        fast_sma_period=10,
        slow_sma_period=30,
        bar_timeframe="1Day",
        lookback_bars=120,
        max_order_notional=500.0,
        max_position_shares=10,
        poll_interval_seconds=60,
        kill_switch_path=Path(".kill_switch"),
        backtest_initial_cash=10_000.0,
        backtest_initial_cash_jpy=None,
        backtest_max_order_notional_jpy=None,
        data_feed=DataFeed.IEX,
        chart_refresh_seconds=15,
        market="auto",
        display_currency="auto",
        fx_usdjpy_manual=None,
    )
    base.update(kwargs)
    return Settings(**base)


def test_japan_initial_cash_defaults_to_one_million_yen():
    s = _settings()
    assert resolve_initial_cash(s, "jp", None) == 1_000_000.0


def test_japan_order_notional_scales_when_us_config():
    s = _settings()
    cash = resolve_initial_cash(s, "jp", None)
    notional, _ = resolve_backtest_limits(s, "jp", cash)
    assert notional >= 500_000.0
