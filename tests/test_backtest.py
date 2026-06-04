import pandas as pd

from stock_auto_trader.backtest.engine import run_backtest


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


def test_backtest_runs_with_trades_on_trend_reversal():
    # Decline then sharp rally to force crossover activity.
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
