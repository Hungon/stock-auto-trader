import dataclasses
from pathlib import Path

import pytest
from alpaca.data.enums import DataFeed
from alpaca.trading.enums import OrderSide

from stock_auto_trader.broker.alpaca import AlpacaBroker
from stock_auto_trader.config import DemoModeError, Settings, demo_build_enabled


def _settings(**overrides) -> Settings:
    base = dict(
        api_key="demo",
        secret_key="demo",
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
        backtest_initial_cash_jpy=1_000_000.0,
        backtest_max_order_notional_jpy=500_000.0,
        data_feed=DataFeed.IEX,
        chart_refresh_seconds=15,
        market="us",
        display_currency="auto",
        fx_usdjpy_manual=None,
        max_daily_loss_usd=0.0,
        max_daily_loss_pct=0.0,
        daily_loss_action="block_orders",
        max_portfolio_drawdown_pct=0.0,
        drawdown_action="kill_switch",
        risk_state_path=Path("./data/runtime/risk_state.json"),
        max_data_age_seconds=0,
        max_daily_bar_age_days=3,
        require_market_open=True,
        allow_premarket=False,
        allow_afterhours=False,
        no_trade_first_minutes=0,
        no_trade_last_minutes=0,
        backtest_slippage_bps=0.0,
        backtest_commission_per_trade=0.0,
        backtest_commission_bps=0.0,
        backtest_execution_mode="next_open",
        log_format="text",
        log_level="INFO",
        log_file=None,
    )
    base.update(overrides)
    return Settings(**base)


def test_demo_build_enabled_by_default(monkeypatch):
    monkeypatch.delenv("DEMO_BUILD", raising=False)
    assert demo_build_enabled() is True


def test_demo_build_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DEMO_BUILD", "false")
    assert demo_build_enabled() is False


def test_orders_disabled_in_demo_even_when_live_confirmed(monkeypatch):
    monkeypatch.delenv("DEMO_BUILD", raising=False)
    live = _settings(trading_mode="live", live_trading_confirmed=True)
    assert live.orders_enabled is False


def test_orders_enabled_when_demo_disabled(monkeypatch):
    monkeypatch.setenv("DEMO_BUILD", "false")
    live = _settings(trading_mode="live", live_trading_confirmed=True)
    assert live.orders_enabled is True
    paper = _settings(trading_mode="paper")
    assert paper.orders_enabled is True


def test_broker_order_methods_blocked_in_demo(monkeypatch):
    monkeypatch.delenv("DEMO_BUILD", raising=False)
    broker = AlpacaBroker(_settings())
    with pytest.raises(DemoModeError):
        broker.submit_market_order("SPY", OrderSide.BUY, 1)
    with pytest.raises(DemoModeError):
        broker.cancel_all_orders()
    with pytest.raises(DemoModeError):
        broker.close_all_positions()
