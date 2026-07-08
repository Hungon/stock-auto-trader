import math

import pandas as pd

from app.opportunity.engine import (
    SETUP_TYPES,
    compute_opportunity_signal,
    compute_opportunity_signal_at_index,
    signal_to_dict,
)


def _bars(closes, volumes=None, highs=None, lows=None):
    n = len(closes)
    idx = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    highs = highs if highs is not None else [c * 1.004 for c in closes]
    lows = lows if lows is not None else [c * 0.996 for c in closes]
    volumes = volumes if volumes is not None else [1_000_000] * n
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=idx,
    )


def _uptrend_closes(n=80, start=100.0):
    """Rising series with small pullbacks so RSI stays finite and mid-high."""
    closes = [start]
    for i in range(1, n):
        step = 1.6 if i % 3 != 0 else -0.9  # net up, with down days
        closes.append(round(closes[-1] + step, 2))
    return closes


def _downtrend_closes(n=80, start=200.0):
    closes = [start]
    for i in range(1, n):
        step = -1.6 if i % 3 != 0 else 0.9
        closes.append(round(closes[-1] + step, 2))
    return closes


def test_neutral_flat_market():
    # Mild early drift then quiet chop; ends just below SMA20 with SMA20 ~= SMA50
    # and mid RSI, so no directional setup matches.
    closes = [100 + i * 0.02 for i in range(40)]
    closes += [100.8 + (0.15 if i % 2 else -0.15) for i in range(40)]
    closes[-1] = 100.55
    sig = compute_opportunity_signal("TEST", "Test", "us", _bars(closes))
    assert sig.opportunity_type == "Neutral / Mixed"
    assert 30 <= sig.opportunity_score <= 70


def test_high_volume_alert():
    closes = [100 + (0.2 if i % 2 else -0.2) for i in range(80)]
    volumes = [1_000_000] * 79 + [3_500_000]  # 3.5x spike on last bar
    sig = compute_opportunity_signal("TEST", "Test", "us", _bars(closes, volumes))
    assert sig.opportunity_type == "High Volume Alert"
    assert sig.volume_ratio is not None and sig.volume_ratio > 2.0
    assert sig.volume_score >= 80


def test_bearish_breakdown():
    closes = _downtrend_closes()
    # Force a fresh 20-day low with a big down day on elevated volume.
    closes[-1] = round(min(closes[-21:-1]) * 0.97, 2)
    lows = [c * 0.996 for c in closes]
    lows[-1] = closes[-1]
    volumes = [1_000_000] * 79 + [2_000_000]
    sig = compute_opportunity_signal(
        "TEST", "Test", "us", _bars(closes, volumes, lows=lows)
    )
    assert sig.opportunity_type == "Bearish Breakdown"
    assert sig.rsi is not None and sig.rsi < 45
    assert sig.confidence == "high"


def test_uptrend_scores_positive():
    closes = _uptrend_closes()
    sig = compute_opportunity_signal("TEST", "Test", "us", _bars(closes))
    assert sig.sma20 is not None and sig.sma50 is not None
    assert sig.sma20 > sig.sma50
    assert sig.momentum_score >= 60
    assert sig.technical_score >= 55
    # An uptrend should fit the trend-following strategies at least "possible".
    trend_fit = next(f for f in sig.strategy_fit if f["strategy_id"] == "ma_trend_20_50")
    assert trend_fit["fit"] in {"strong", "possible"}


def test_momentum_breakout():
    closes = _uptrend_closes()
    prior_high20 = max((c * 1.004) for c in closes[-21:-1])
    closes[-1] = round(prior_high20 * 1.02, 2)  # close above prior 20-day high
    highs = [c * 1.004 for c in closes]
    highs[-1] = closes[-1]
    volumes = [1_000_000] * 79 + [1_800_000]  # 1.8x volume confirmation
    sig = compute_opportunity_signal(
        "TEST", "Test", "us", _bars(closes, volumes, highs=highs)
    )
    assert sig.opportunity_type == "Momentum Breakout"
    assert sig.opportunity_score >= 65


def test_new_high_candidate():
    sig = compute_opportunity_signal("TEST", "Test", "us", _bars(_uptrend_closes()))
    assert sig.opportunity_type == "New High Candidate"
    assert sig.sma20 > sig.sma50


def test_trend_continuation():
    up = _uptrend_closes(70)
    up += [round(up[-1] * (1 - 0.005 * i), 2) for i in range(1, 6)]  # modest pullback
    sig = compute_opportunity_signal("TEST", "Test", "us", _bars(up))
    assert sig.opportunity_type == "Trend Continuation"
    assert sig.dist_from_high20_pct is not None and sig.dist_from_high20_pct < 0


def test_weakness_short_watch():
    sig = compute_opportunity_signal("TEST", "Test", "us", _bars(_downtrend_closes()))
    assert sig.opportunity_type == "Weakness / Short-Watch"
    assert sig.rsi is not None and sig.rsi < 45


def test_at_index_matches_full_compute():
    up = _uptrend_closes()
    bars = _bars(up)
    full = compute_opportunity_signal("TEST", "Test", "us", bars)
    last = compute_opportunity_signal_at_index("TEST", "Test", "us", bars, len(up) - 1)
    neg = compute_opportunity_signal_at_index("TEST", "Test", "us", bars, -1)
    assert last.opportunity_type == full.opportunity_type
    assert last.opportunity_score == full.opportunity_score
    assert neg.opportunity_score == full.opportunity_score
    # An earlier index should compute without error and may differ.
    early = compute_opportunity_signal_at_index("TEST", "Test", "us", bars, 40)
    assert early.opportunity_score is not None


def test_setup_types_registry():
    assert len(SETUP_TYPES) == len(set(SETUP_TYPES))
    for key in ("Momentum Breakout", "Neutral / Mixed", "Bearish Breakdown"):
        assert key in SETUP_TYPES


def test_short_series_is_safe():
    closes = [100, 101, 102, 101, 103, 104, 105, 104, 106, 107]
    sig = compute_opportunity_signal("TEST", "Test", "jp", _bars(closes))
    assert sig.sma50 is None
    assert sig.opportunity_type == "Neutral / Mixed"
    assert sig.confidence == "low"


def test_signal_dict_is_json_safe():
    closes = _uptrend_closes()
    d = signal_to_dict(compute_opportunity_signal("TEST", "Test", "us", _bars(closes)))
    for key, value in d.items():
        if isinstance(value, float):
            assert not math.isnan(value) and not math.isinf(value), key
    assert isinstance(d["explanation"], list)
    assert isinstance(d["strategy_fit"], list)
