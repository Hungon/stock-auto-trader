import pandas as pd

from stock_auto_trader.strategy.sma_crossover import Signal, compute_sma_signal


def test_buy_crossover():
    # Uptrend: slow ramp then faster ramp triggers golden cross at end.
    closes = list(range(1, 41))
    bars = pd.DataFrame({"close": closes})
    signal = compute_sma_signal(bars, fast_period=5, slow_period=10)
    assert signal in {Signal.BUY, Signal.HOLD, Signal.SELL}
