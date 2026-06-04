from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import yfinance as yf

from stock_auto_trader.config import Settings
from stock_auto_trader.data.bars_util import OHLCV, sanitize_bars

_INTERVAL_MAP = {
    "1Min": "1m",
    "5Min": "5m",
    "15Min": "15m",
    "1Hour": "1h",
    "1Day": "1d",
}


def _interval(settings: Settings) -> str:
    return _INTERVAL_MAP.get(settings.bar_timeframe, "1d")


def fetch_bars_between(
    symbol: str,
    start: date,
    end: date,
    settings: Settings,
) -> pd.DataFrame:
    interval = _interval(settings)
    # TSE quotes on Yahoo are in nominal JPY; auto_adjust can skew levels vs broker sites.
    auto_adjust = not symbol.upper().endswith(".T")
    end_inclusive = end + pd.Timedelta(days=1)
    df = yf.download(
        symbol,
        start=start.isoformat(),
        end=end_inclusive.isoformat(),
        interval=interval,
        auto_adjust=auto_adjust,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        raise ValueError(f"No Yahoo Finance data for {symbol}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns=str.lower)
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns from Yahoo: {missing}")

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    df = sanitize_bars(df[OHLCV])
    if df.empty:
        raise ValueError(f"No complete OHLCV rows for {symbol}")
    _sanity_check_jpy(symbol, float(df["close"].iloc[-1]))
    return df


def _sanity_check_jpy(symbol: str, close: float) -> None:
    """Catch wrong tickers (e.g. 6758 vs 6758.T) that return USD-scale prices."""
    sym = symbol.upper()
    if not sym.endswith(".T"):
        return

    try:
        info = yf.Ticker(sym).fast_info
        currency = str(getattr(info, "currency", "JPY") or "JPY").upper()
        if currency == "USD":
            raise ValueError(
                f"{sym} is returning USD prices on Yahoo. "
                "Select Japan (TSE) and use the .T ticker (6758.T for Sony)."
            )
    except ValueError:
        raise
    except Exception:
        pass

    # Obvious bad quotes (e.g. ~$7 mistaken for ¥1100 after FX).
    if close < 500:
        raise ValueError(
            f"{sym} last close ¥{close:,.0f} looks too low for a TSE quote. "
            "Use the .T suffix (e.g. 6758.T for Sony) and Japan (TSE) market."
        )
    if sym == "6758.T" and close < 2500:
        raise ValueError(
            f"Sony (6758.T) close ¥{close:,.0f} is abnormally low (expected ~¥3,000+). "
            "Set market to Japan (TSE), currency JPY (¥), and reload."
        )


def fetch_latest_tick(symbol: str, settings: Settings) -> dict:
    sym = symbol.upper()
    auto_adjust = not sym.endswith(".T")
    ticker = yf.Ticker(sym)
    hist = ticker.history(
        period="5d", interval=_interval(settings), auto_adjust=auto_adjust
    )
    if hist.empty:
        raise ValueError(f"No recent data for {symbol}")

    hist = hist.rename(columns=str.lower)
    row = hist.iloc[-1]
    ts = hist.index[-1]
    time_str = ts.strftime("%Y-%m-%d %H:%M") if _interval(settings) != "1d" else ts.strftime(
        "%Y-%m-%d"
    )
    close = float(row["close"])
    _sanity_check_jpy(sym, close)
    open_ = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    vol = float(row["volume"])

    return {
        "symbol": symbol,
        "time": time_str,
        "market": "jp",
        "bar": {
            "time": time_str,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        },
        "quote": {
            "bid": close,
            "ask": close,
            "bid_size": 0,
            "ask_size": 0,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
