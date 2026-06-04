from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestBarRequest,
    StockLatestQuoteRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from stock_auto_trader.config import Settings


def _parse_timeframe(value: str) -> TimeFrame:
    mapping = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    if value not in mapping:
        raise ValueError(f"Unsupported BAR_TIMEFRAME: {value}")
    return mapping[value]


class AlpacaBroker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._trading = TradingClient(
            settings.api_key,
            settings.secret_key,
            url_override=settings.base_url,
        )
        self._data = StockHistoricalDataClient(
            settings.api_key,
            settings.secret_key,
        )
        self._timeframe = _parse_timeframe(settings.bar_timeframe)

    def get_account_summary(self) -> dict:
        account = self._trading.get_account()
        return {
            "status": str(account.status),
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "pattern_day_trader": account.pattern_day_trader,
        }

    def get_position_qty(self, symbol: str) -> float:
        try:
            position = self._trading.get_open_position(symbol)
            return float(position.qty)
        except Exception:
            return 0.0

    def fetch_bars(self, symbol: str, limit: int) -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        # Pull extra calendar days so rolling windows are filled.
        start = end - timedelta(days=limit * 3)
        return self.fetch_bars_between(symbol, start, end, limit=limit)

    def fetch_bars_between(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        *,
        limit: int | None = None,
    ) -> pd.DataFrame:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=self._timeframe,
            start=start,
            end=end,
            limit=limit,
            feed=self.settings.data_feed,
        )
        bars = self._data.get_stock_bars(request).df
        if bars.empty:
            raise ValueError(f"No bar data returned for {symbol} between {start} and {end}")

        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level="symbol")

        bars = bars.sort_index()
        return bars.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]

    def submit_market_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: int,
    ) -> str:
        if qty <= 0:
            raise ValueError("Order quantity must be positive")

        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        submitted = self._trading.submit_order(order)
        return str(submitted.id)

    def is_market_open(self) -> bool:
        clock = self._trading.get_clock()
        return bool(clock.is_open)

    def fetch_latest_tick(self, symbol: str) -> dict:
        """Latest bar and quote for live chart updates."""
        bar_req = StockLatestBarRequest(
            symbol_or_symbols=symbol,
            feed=self.settings.data_feed,
        )
        quote_req = StockLatestQuoteRequest(
            symbol_or_symbols=symbol,
            feed=self.settings.data_feed,
        )
        bar_map = self._data.get_stock_latest_bar(bar_req)
        quote_map = self._data.get_stock_latest_quote(quote_req)

        bar = bar_map[symbol]
        quote = quote_map[symbol]
        ts = bar.timestamp
        time_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]

        return {
            "symbol": symbol,
            "time": time_str,
            "bar": {
                "time": time_str,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            },
            "quote": {
                "bid": float(quote.bid_price),
                "ask": float(quote.ask_price),
                "bid_size": float(quote.bid_size),
                "ask_size": float(quote.ask_size),
            },
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
