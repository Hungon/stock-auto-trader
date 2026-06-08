# stock-auto-trader

Python app for **US stock auto-trading on Alpaca** (SMA crossover) plus a **local web UI** for charting and **multi-strategy backtesting** on US and **Japan (TSE)** symbols.

> **Risk warning:** Automated trading can lose money quickly. This project is educational tooling, not financial advice. Test thoroughly on paper before using real money.

## Features

- **Live trading (US only):** SMA crossover on Alpaca paper or live accounts
- **Japan (TSE):** OHLCV bars via [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance) — chart and backtest only (no orders; **delayed data, not for production**)
- **Web UI:** TradingView-style chart + dedicated backtest page ([Lightweight Charts](https://www.tradingview.com/lightweight-charts/))
- **Six backtest strategies** with compare-all and multi-symbol scan
- **USD / JPY** display with live or manual FX
- Risk limits, kill switch, and `LIVE_TRADING_CONFIRMED` guard for live orders
- **CLI:** `status`, `run-once`, `run`, `backtest`, `backtest-scan`, `chart`, `kill-switch`, `export-trades`, `walk-forward`
- **Risk controls:** daily loss limit, portfolio drawdown kill switch, stale data protection, market-hours validation
- **Backtest realism:** slippage, commission, next-bar execution (`next_open` default)
- **Structured logging:** text or JSON via `LOG_FORMAT`

## Screenshots

### Chart UI

Candlesticks, volume, SMA overlays, and buy/sell markers (Toyota `7203.T`, Japan TSE).

### Backtest — compare all strategies

Equity curves and strategy comparison table for the same symbol and date range.

Backtest — strategy comparison and equity curves

## Quick start

### 1. Alpaca account (US trading)

1. Sign up at [https://alpaca.markets/](https://alpaca.markets/)
2. Create API keys (paper recommended first)
3. In `.env`: `TRADING_MODE=paper` and `ALPACA_BASE_URL=https://paper-api.alpaca.markets`

Japan-only chart/backtest can run **without** Alpaca keys. US symbols use Alpaca (or demo synthetic data if keys are missing); Japan symbols always use **yfinance**.

### 2. Install

```bash
git clone https://github.com/Hungon/stock-auto-trader.git
cd stock-auto-trader
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
# Edit .env with your API keys (optional for Japan backtest-only)
```

### 3. Check status (no orders)

```bash
stock-trader status
```

### 4. Web UI (chart + backtest)

```bash
stock-trader chart
```


| URL                                                              | Purpose                                                        |
| ---------------------------------------------------------------- | -------------------------------------------------------------- |
| [http://127.0.0.1:8765/](http://127.0.0.1:8765/)                 | Chart — candlesticks, SMAs, volume, live refresh               |
| [http://127.0.0.1:8765/backtest](http://127.0.0.1:8765/backtest) | Backtest — pick strategy, **Compare all**, or **Scan presets** |


Toolbar: market (Japan / US), symbol, date range, currency. Default end date is **yesterday** (today’s bar is often incomplete on Yahoo).

### 5. Live trading (US, careful)

With `LIVE_TRADING_CONFIRMED=no`, `run-once` evaluates signals but does **not** send orders:

```bash
stock-trader run-once
```

To enable live orders:

```env
TRADING_MODE=live
ALPACA_BASE_URL=https://api.alpaca.markets
LIVE_TRADING_CONFIRMED=yes
```

```bash
stock-trader run-once   # single tick
stock-trader run        # loop (Ctrl+C to stop)
```

Live loop uses the **SMA crossover** from `.env` (`FAST_SMA_PERIOD` / `SLOW_SMA_PERIOD`) on your `SYMBOL`. Backtest strategies are simulation-only.

## Backtest strategies

All strategies are long-only and share position limits from `.env` (Japan backtests scale cash/notional for yen). Default execution is **next bar open** (`BACKTEST_EXECUTION_MODE=next_open`); use `same_close` to match legacy behavior. Strategies using **MA200** need ~200+ daily bars (use a range of at least ~2 years).


| ID                   | Summary                                                             |
| -------------------- | ------------------------------------------------------------------- |
| `sma_crossover`      | Fast/slow SMA cross from `.env` + volume filter; stop & trail       |
| `ma_cross_20_50`     | Golden cross 20/50 + MA200 + rising MA50; stops, trail, take-profit |
| `ma_trend_20_50`     | Golden/death cross above MA200 with volume                          |
| `rsi_mean_reversion` | RSI oversold bounce above MA200; take-profit & stop                 |
| `breakout_20`        | New 20-day high + volume in uptrend; trail & take-profit            |
| `trend_risk_control` | Filtered golden cross + RSI band + volume; layered exits            |


`pair_trading` and `multi_factor` are placeholders (need two symbols or a stock universe).

**Metrics:** return vs buy & hold, max drawdown, win rate, Sharpe, profit factor, exposure, trade list.

### CLI

```bash
# One strategy
stock-trader backtest --market jp --symbol 6758.T --strategy ma_cross_20_50

# All strategies on one symbol
stock-trader backtest --market jp --symbol 6758.T --compare

# All strategies × multiple symbols
stock-trader backtest-scan --symbols 6758.T,7203.T,SPY,AAPL

# Custom range (end before today avoids incomplete bars)
stock-trader backtest --start 2022-01-01 --end 2025-06-03 --symbol SPY

# Local CSV (timestamp/date + open,high,low,close,volume)
stock-trader backtest --csv ./data/spy.csv --symbol SPY

# Export trade journal
stock-trader backtest --symbol SPY --strategy sma_crossover --export-trades trades.csv
stock-trader export-trades --format csv --output trades.csv --symbol SPY
stock-trader export-trades --input backtest-result.json --format csv --output trades.csv

# Walk-forward out-of-sample testing
stock-trader walk-forward --symbol SPY --strategy sma_crossover \
  --start 2018-01-01 --end 2025-01-01 --train-years 3 --test-months 6
stock-trader walk-forward --symbol SPY --compare --start 2018-01-01 --end 2025-01-01
```

List strategy IDs: `GET http://127.0.0.1:8765/api/strategies` (with chart server running).

### Kill switch

```bash
stock-trader kill-switch --enable
stock-trader kill-switch --disable
```

## US vs Japan


|                   | **US (e.g. SPY, AAPL)** | **Japan (e.g. 7203.T)**                     |
| ----------------- | ----------------------- | ------------------------------------------- |
| **Data**          | Alpaca (API keys)       | yfinance → Yahoo Finance (delayed; research only) |
| **Auto-trading**  | Yes (paper/live)        | No — chart & backtest only                  |
| **Symbol format** | `AAPL`, `SPY`           | `7203.T` or `7203` (Toyota)                 |
| **Aliases**       | —                       | e.g. `SONY` → `6758.T` when market is Japan |


```env
MARKET=jp
SYMBOL=7203.T
```

Popular presets are in the chart/backtest toolbar (Toyota, Sony, SoftBank, MUFG, Nintendo, etc.).

## Japan market data (yfinance)

Japan (TSE) symbols are fetched with **[yfinance](https://github.com/ranaroussi/yfinance)** — a Python wrapper around Yahoo Finance. It is installed automatically with this project (`yfinance>=0.2.40` in `pyproject.toml`). **No API key or account is required.**

> **Not production-ready:** Yahoo data via yfinance is **delayed** (often 15–20 minutes or more for intraday quotes, and end-of-day bars may lag). It is suitable for **research, charting, and backtesting only** — not for live trading decisions, real-time alerts, or any production workflow that needs timely prices.

### When yfinance is used

| Use case | Japan (`.T` tickers) | US tickers |
| -------- | -------------------- | ---------- |
| Web chart / live refresh | yfinance | Alpaca |
| Backtest / backtest-scan | yfinance | Alpaca |
| Walk-forward / export-trades | yfinance | Alpaca |
| Live auto-trading (`run`, `run-once`) | Not supported | Alpaca |

Routing is automatic: symbols ending in `.T` or 4-digit codes (e.g. `7203`) resolve to market `jp` and call `stock_auto_trader.data.yfinance_provider`.

### Symbol format

- Use **Tokyo suffix**: `7203.T` (Toyota), `6758.T` (Sony), `9984.T` (SoftBank)
- Bare codes work when `MARKET=jp` or auto-detect: `7203` → `7203.T`
- Aliases when market is Japan: `SONY` → `6758.T`
- Prices are in **JPY**. The app sanity-checks `.T` tickers so a wrong symbol (e.g. missing `.T`) does not silently return USD-scale prices.

### Timeframes

`BAR_TIMEFRAME` in `.env` maps to Yahoo intervals:

| `BAR_TIMEFRAME` | Yahoo interval |
| --------------- | -------------- |
| `1Day` (default) | `1d` |
| `1Hour` | `1h` |
| `15Min` | `15m` |
| `5Min` | `5m` |
| `1Min` | `1m` |

Daily bars are the most reliable for Japan backtests. Intraday history depends on Yahoo’s coverage and may be limited compared to US symbols.

### CLI examples

```bash
# Backtest Sony on TSE data
stock-trader backtest --market jp --symbol 6758.T --strategy sma_crossover

# Scan multiple Japan names
stock-trader backtest-scan --symbols 7203.T,6758.T,9984.T

# Japan preset in .env
# MARKET=jp
# SYMBOL=7203.T
```

### CSV alternative

You can bypass yfinance and backtest from a local file (any market):

```bash
stock-trader backtest --csv ./data/7203.csv --symbol 7203.T --market jp
```

CSV must include `timestamp` or `date` plus `open`, `high`, `low`, `close`, `volume`.

### Limitations

- **Delayed, not production-grade** — yfinance reads public Yahoo endpoints with **no SLA**. Quotes and bars can be delayed; intraday refresh in the chart UI reflects Yahoo’s lag, not a live market feed. Do **not** rely on this data for production trading, execution, or time-sensitive decisions.
- **Unofficial data** — not a broker feed. Gaps, revisions, and corporate-action handling may differ from licensed vendors.
- **No Japan orders** — chart and simulation only; Alpaca remains US-only.
- **End date** — default backtest/chart end is **yesterday** because today’s daily bar is often incomplete on Yahoo.
- **FX** — cross-currency display also uses Yahoo (`USDJPY=X`) unless you set `FX_USDJPY` manually.

Implementation: `src/stock_auto_trader/data/yfinance_provider.py`.

## Currency (USD / JPY)

Toolbar: **USD**, **JPY**, or **Auto** (JPY for Japan, USD for US). Cross-currency view uses Yahoo `USDJPY=X` unless overridden:

```env
DISPLAY_CURRENCY=auto
FX_USDJPY=150.0
```

## Configuration


| Variable                                                    | Description                                               |
| ----------------------------------------------------------- | --------------------------------------------------------- |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`                      | Alpaca credentials (required for US live/backtest data)   |
| `ALPACA_BASE_URL`                                           | Must match `TRADING_MODE`                                 |
| `ALPACA_DATA_FEED`                                          | `iex` (free) or `sip` (paid)                              |
| `TRADING_MODE`                                              | `live` or `paper`                                         |
| `LIVE_TRADING_CONFIRMED`                                    | `yes` to submit live orders                               |
| `MARKET`                                                    | `auto`, `us`, or `jp`                                     |
| `SYMBOL`                                                    | Default ticker                                            |
| `DISPLAY_CURRENCY`                                          | `auto`, `usd`, or `jpy`                                   |
| `FX_USDJPY`                                                 | Optional fixed JPY per 1 USD                              |
| `FAST_SMA_PERIOD` / `SLOW_SMA_PERIOD`                       | Live SMA crossover & `sma_crossover` backtest             |
| `BAR_TIMEFRAME`                                             | e.g. `1Day`, `5Min`, `1Min`                               |
| `LOOKBACK_BARS`                                             | Bars fetched for live loop                                |
| `CHART_REFRESH_SECONDS`                                     | Chart live refresh interval                               |
| `MAX_ORDER_NOTIONAL` / `MAX_POSITION_SHARES`                | Risk caps                                                 |
| `POLL_INTERVAL_SECONDS`                                     | Live loop delay                                           |
| `KILL_SWITCH_PATH`                                          | File path for kill switch                                 |
| `MAX_DAILY_LOSS_USD` / `MAX_DAILY_LOSS_PCT`                 | Daily loss limits (0 = off)                               |
| `DAILY_LOSS_ACTION`                                         | `block_orders`, `kill_switch`, or `liquidate`             |
| `MAX_PORTFOLIO_DRAWDOWN_PCT`                                | Peak-to-trough drawdown limit (0 = off)                   |
| `DRAWDOWN_ACTION`                                           | Action when drawdown breached                             |
| `RISK_STATE_PATH`                                           | Persisted equity state (`./data/runtime/risk_state.json`) |
| `MAX_DATA_AGE_SECONDS`                                      | Stale intraday bar threshold (0 = auto)                   |
| `MAX_DAILY_BAR_AGE_DAYS`                                    | Stale daily bar threshold                                 |
| `REQUIRE_MARKET_OPEN`                                       | Block orders when market closed                           |
| `ALLOW_PREMARKET` / `ALLOW_AFTERHOURS`                      | Extended hours trading                                    |
| `NO_TRADE_FIRST_MINUTES` / `NO_TRADE_LAST_MINUTES`          | Session open/close buffers                                |
| `BACKTEST_SLIPPAGE_BPS`                                     | Simulated slippage per fill                               |
| `BACKTEST_COMMISSION_PER_TRADE` / `BACKTEST_COMMISSION_BPS` | Simulated commissions                                     |
| `BACKTEST_EXECUTION_MODE`                                   | `same_close`, `next_open`, or `next_close`                |
| `LOG_FORMAT`                                                | `text` or `json`                                          |
| `LOG_LEVEL`                                                 | Logging level                                             |
| `LOG_FILE`                                                  | Optional log file path                                    |
| `BACKTEST_INITIAL_CASH`                                     | US / default starting cash                                |
| `BACKTEST_INITIAL_CASH_JPY`                                 | Optional yen starting cash                                |
| `BACKTEST_MAX_ORDER_NOTIONAL_JPY`                           | Optional per-buy cap in yen                               |


## Live trading logic (SMA only)

- **Buy** when fast SMA crosses above slow SMA (flat position)
- **Sell** when fast SMA crosses below slow SMA (long position)
- Uses configured `BAR_TIMEFRAME` (default daily)
- Pre-order risk gate checks: kill switch, daily loss, drawdown, stale data, market hours, notional limits

## Disclaimer

You are responsible for compliance, taxes, and losses. Backtest results are simulations; configure slippage and commission for realism. Past performance does not predict future results.