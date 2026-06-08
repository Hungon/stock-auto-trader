import pandas as pd
import pytest

from stock_auto_trader.backtest.engine import run_backtest
from stock_auto_trader.backtest.execution import (
    FillParams,
    apply_slippage,
    calc_commission,
)
from stock_auto_trader.config import Settings
from stock_auto_trader.config_validation import validate_settings
from stock_auto_trader.risk.stale_data import check_stale_data


def _bars_from_closes(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=idx,
    )


def _minimal_settings(**overrides) -> Settings:
    defaults = dict(
        api_key="key",
        secret_key="secret",
        base_url="https://paper-api.alpaca.markets",
        trading_mode="paper",
        live_trading_confirmed=False,
        symbol="SPY",
        fast_sma_period=10,
        slow_sma_period=30,
        bar_timeframe="1Day",
        lookback_bars=120,
        max_order_notional=500,
        max_position_shares=10,
        poll_interval_seconds=60,
        kill_switch_path=__import__("pathlib").Path(".kill_switch"),
        backtest_initial_cash=10_000,
        backtest_initial_cash_jpy=None,
        backtest_max_order_notional_jpy=None,
        data_feed=__import__("alpaca.data.enums", fromlist=["DataFeed"]).DataFeed.IEX,
        chart_refresh_seconds=15,
        market="us",
        display_currency="auto",
        fx_usdjpy_manual=None,
        max_daily_loss_usd=0,
        max_daily_loss_pct=0,
        daily_loss_action="block_orders",
        max_portfolio_drawdown_pct=0,
        drawdown_action="kill_switch",
        risk_state_path=__import__("pathlib").Path("./data/runtime/risk_state.json"),
        max_data_age_seconds=0,
        max_daily_bar_age_days=3,
        require_market_open=True,
        allow_premarket=False,
        allow_afterhours=False,
        no_trade_first_minutes=0,
        no_trade_last_minutes=0,
        backtest_slippage_bps=0,
        backtest_commission_per_trade=0,
        backtest_commission_bps=0,
        backtest_execution_mode="next_open",
        log_format="text",
        log_level="INFO",
        log_file=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_backtest_runs_with_trades_on_trend_reversal():
    down = [100 - i * 0.5 for i in range(40)]
    up = [80 + i * 2.0 for i in range(40)]
    bars = _bars_from_closes(down + up)

    result = run_backtest(
        bars,
        symbol="TEST",
        fast_period=5,
        slow_period=10,
        initial_cash=10_000,
        max_order_notional=5_000,
        max_position_shares=100,
    )

    assert result.final_equity > 0
    assert result.num_trades >= 0
    assert len(result.equity_curve) == len(bars)


def test_slippage_and_commission():
    assert apply_slippage(100.0, "buy", 10) == pytest.approx(100.1)
    assert apply_slippage(100.0, "sell", 10) == pytest.approx(99.9)
    assert calc_commission(1000, commission_per_trade=1.0, commission_bps=10) == pytest.approx(
        2.0
    )


def test_next_open_defers_fill_to_next_bar():
    closes = [10.0] * 15 + [20.0] * 15
    bars = _bars_from_closes(closes)
    bars.iloc[14, bars.columns.get_loc("open")] = 12.0
    bars.iloc[15, bars.columns.get_loc("open")] = 18.0

    same = run_backtest(
        bars,
        symbol="TEST",
        fast_period=3,
        slow_period=5,
        initial_cash=10_000,
        max_order_notional=5_000,
        max_position_shares=100,
        fill_params=FillParams(execution_mode="same_close"),
    )
    nxt = run_backtest(
        bars,
        symbol="TEST",
        fast_period=3,
        slow_period=5,
        initial_cash=10_000,
        max_order_notional=5_000,
        max_position_shares=100,
        fill_params=FillParams(execution_mode="next_open"),
    )

    if same.trades and nxt.trades:
        assert same.trades[0].timestamp <= nxt.trades[0].timestamp


def test_final_bar_signal_not_filled_in_next_open():
    bars = _bars_from_closes([100.0] * 20)
    result = run_backtest(
        bars,
        symbol="TEST",
        fast_period=3,
        slow_period=5,
        initial_cash=10_000,
        max_order_notional=5_000,
        max_position_shares=100,
        fill_params=FillParams(execution_mode="next_open"),
    )
    if result.trades:
        last_trade_ts = result.trades[-1].timestamp
        last_bar_ts = bars.index[-1].to_pydatetime().replace(tzinfo=None)
        assert last_trade_ts.replace(tzinfo=None) <= last_bar_ts


def test_next_close_defers_fill():
    closes = [10.0] * 20
    bars = _bars_from_closes(closes)
    bars.iloc[10, bars.columns.get_loc("close")] = 25.0

    result = run_backtest(
        bars,
        symbol="TEST",
        fast_period=3,
        slow_period=5,
        initial_cash=10_000,
        max_order_notional=5_000,
        max_position_shares=100,
        fill_params=FillParams(execution_mode="next_close"),
    )
    for trade in result.trades:
        assert trade.execution_mode == "next_close"


def test_same_close_matches_immediate_fill():
    closes = [100 - i for i in range(30)] + [70 + i for i in range(30)]
    bars = _bars_from_closes(closes)
    result = run_backtest(
        bars,
        symbol="TEST",
        fast_period=5,
        slow_period=10,
        initial_cash=10_000,
        max_order_notional=5_000,
        max_position_shares=100,
        fill_params=FillParams(execution_mode="same_close"),
    )
    if result.trades:
        assert result.trades[0].execution_mode == "same_close"


def test_config_validation_rejects_invalid_execution_mode():
    settings = _minimal_settings(backtest_execution_mode="invalid")
    result = validate_settings(settings)
    assert not result.valid


def test_config_validation_warns_live_without_confirmation():
    settings = _minimal_settings(
        trading_mode="live",
        base_url="https://api.alpaca.markets",
        live_trading_confirmed=False,
    )
    result = validate_settings(settings)
    assert result.valid
    assert any(w.field == "LIVE_TRADING_CONFIRMED" for w in result.warnings)


def test_stale_daily_data_detected():
    old_closes = [100.0] * 10
    bars = _bars_from_closes(old_closes)
    bars.index = pd.date_range("2020-01-01", periods=10, freq="D", tz="UTC")
    settings = _minimal_settings(max_daily_bar_age_days=3, bar_timeframe="1Day")
    check = check_stale_data(settings, "SPY", bars)
    assert check.stale
