from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from alpaca.data.enums import DataFeed

from stock_auto_trader.markets.detect import normalize_symbol

LIVE_BASE_URL = "https://api.alpaca.markets"
PAPER_BASE_URL = "https://paper-api.alpaca.markets"


@dataclass(frozen=True)
class Settings:
    api_key: str
    secret_key: str
    base_url: str
    trading_mode: str
    live_trading_confirmed: bool
    symbol: str
    fast_sma_period: int
    slow_sma_period: int
    bar_timeframe: str
    lookback_bars: int
    max_order_notional: float
    max_position_shares: int
    poll_interval_seconds: int
    kill_switch_path: Path
    backtest_initial_cash: float
    backtest_initial_cash_jpy: float | None
    backtest_max_order_notional_jpy: float | None
    data_feed: DataFeed
    chart_refresh_seconds: int
    market: str
    display_currency: str
    fx_usdjpy_manual: float | None

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"

    @property
    def orders_enabled(self) -> bool:
        if not self.is_live:
            return True
        return self.live_trading_confirmed


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    return int(raw)


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    return float(raw)


def load_settings(env_path: Path | None = None) -> Settings:
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

    trading_mode = os.getenv("TRADING_MODE", "paper").strip().lower()
    base_url = os.getenv("ALPACA_BASE_URL", PAPER_BASE_URL).strip().rstrip("/")

    if trading_mode not in {"live", "paper"}:
        raise ValueError('TRADING_MODE must be "live" or "paper"')

    expected_base = LIVE_BASE_URL if trading_mode == "live" else PAPER_BASE_URL
    if base_url != expected_base:
        raise ValueError(
            f"TRADING_MODE={trading_mode} requires ALPACA_BASE_URL={expected_base}, "
            f"got {base_url}"
        )

    fast = _int("FAST_SMA_PERIOD", 10)
    slow = _int("SLOW_SMA_PERIOD", 30)
    if fast >= slow:
        raise ValueError("FAST_SMA_PERIOD must be less than SLOW_SMA_PERIOD")

    market = os.getenv("MARKET", "auto").strip().lower()
    if market not in {"auto", "us", "jp"}:
        raise ValueError('MARKET must be "auto", "us", or "jp"')

    default_symbol = "7203.T" if market == "jp" else "SPY"
    symbol = normalize_symbol(
        os.getenv("SYMBOL", default_symbol).strip(),
        market if market != "auto" else None,
    )

    return Settings(
        api_key=_require("ALPACA_API_KEY"),
        secret_key=_require("ALPACA_SECRET_KEY"),
        base_url=base_url,
        trading_mode=trading_mode,
        live_trading_confirmed=os.getenv("LIVE_TRADING_CONFIRMED", "no").strip().lower()
        == "yes",
        symbol=symbol,
        market=market,
        fast_sma_period=fast,
        slow_sma_period=slow,
        bar_timeframe=os.getenv("BAR_TIMEFRAME", "1Day").strip(),
        lookback_bars=_int("LOOKBACK_BARS", 120),
        max_order_notional=_float("MAX_ORDER_NOTIONAL", 500),
        max_position_shares=_int("MAX_POSITION_SHARES", 10),
        poll_interval_seconds=_int("POLL_INTERVAL_SECONDS", 60),
        kill_switch_path=Path(os.getenv("KILL_SWITCH_PATH", ".kill_switch")),
        backtest_initial_cash=_float("BACKTEST_INITIAL_CASH", 10_000),
        backtest_initial_cash_jpy=_optional_float("BACKTEST_INITIAL_CASH_JPY"),
        backtest_max_order_notional_jpy=_optional_float(
            "BACKTEST_MAX_ORDER_NOTIONAL_JPY"
        ),
        data_feed=_parse_data_feed(os.getenv("ALPACA_DATA_FEED", "iex")),
        chart_refresh_seconds=max(5, _int("CHART_REFRESH_SECONDS", 15)),
        display_currency=os.getenv("DISPLAY_CURRENCY", "auto").strip().lower(),
        fx_usdjpy_manual=_optional_float("FX_USDJPY"),
    )


def _optional_float(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return float(raw)


def _parse_data_feed(value: str) -> DataFeed:
    key = value.strip().lower()
    mapping = {
        "iex": DataFeed.IEX,
        "sip": DataFeed.SIP,
        "delayed_sip": DataFeed.DELAYED_SIP,
        "otc": DataFeed.OTC,
    }
    if key not in mapping:
        raise ValueError(
            f"ALPACA_DATA_FEED must be one of {list(mapping)}; got {value!r}"
        )
    return mapping[key]
