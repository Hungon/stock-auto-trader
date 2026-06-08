"""Application settings loaded from environment variables (.env)."""
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
    """Runtime configuration for trading, backtests, risk, and logging."""

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
    # Daily loss limit
    max_daily_loss_usd: float
    max_daily_loss_pct: float
    daily_loss_action: str
    # Portfolio drawdown
    max_portfolio_drawdown_pct: float
    drawdown_action: str
    risk_state_path: Path
    # Stale data
    max_data_age_seconds: int
    max_daily_bar_age_days: int
    # Market hours
    require_market_open: bool
    allow_premarket: bool
    allow_afterhours: bool
    no_trade_first_minutes: int
    no_trade_last_minutes: int
    # Backtest realism
    backtest_slippage_bps: float
    backtest_commission_per_trade: float
    backtest_commission_bps: float
    backtest_execution_mode: str
    # Logging
    log_format: str
    log_level: str
    log_file: Path | None

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"

    @property
    def orders_enabled(self) -> bool:
        """Paper mode always allows orders; live requires LIVE_TRADING_CONFIRMED=yes."""
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


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _optional_path(name: str) -> Path | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return Path(raw)


def load_settings(env_path: Path | None = None) -> Settings:
    """Load and parse settings from .env; raises ValueError on invalid combos."""
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
        max_daily_loss_usd=_float("MAX_DAILY_LOSS_USD", 0),
        max_daily_loss_pct=_float("MAX_DAILY_LOSS_PCT", 0),
        daily_loss_action=os.getenv("DAILY_LOSS_ACTION", "block_orders").strip().lower(),
        max_portfolio_drawdown_pct=_float("MAX_PORTFOLIO_DRAWDOWN_PCT", 0),
        drawdown_action=os.getenv("DRAWDOWN_ACTION", "kill_switch").strip().lower(),
        risk_state_path=Path(
            os.getenv("RISK_STATE_PATH", "./data/runtime/risk_state.json")
        ),
        max_data_age_seconds=_int("MAX_DATA_AGE_SECONDS", 0),
        max_daily_bar_age_days=_int("MAX_DAILY_BAR_AGE_DAYS", 3),
        require_market_open=_bool("REQUIRE_MARKET_OPEN", True),
        allow_premarket=_bool("ALLOW_PREMARKET", False),
        allow_afterhours=_bool("ALLOW_AFTERHOURS", False),
        no_trade_first_minutes=_int("NO_TRADE_FIRST_MINUTES", 0),
        no_trade_last_minutes=_int("NO_TRADE_LAST_MINUTES", 0),
        backtest_slippage_bps=_float("BACKTEST_SLIPPAGE_BPS", 0),
        backtest_commission_per_trade=_float("BACKTEST_COMMISSION_PER_TRADE", 0),
        backtest_commission_bps=_float("BACKTEST_COMMISSION_BPS", 0),
        backtest_execution_mode=os.getenv(
            "BACKTEST_EXECUTION_MODE", "next_open"
        ).strip().lower(),
        log_format=os.getenv("LOG_FORMAT", "text").strip().lower(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        log_file=_optional_path("LOG_FILE"),
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
