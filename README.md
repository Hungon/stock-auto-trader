# stock-auto-trader

Python CLI that trades US stocks on **Alpaca** using a **simple moving average (SMA) crossover** strategy.

> **Risk warning:** Automated trading can lose money quickly. This project is educational tooling, not financial advice. Test thoroughly on paper before using real money.

## Features

- SMA crossover signals (fast vs slow moving average)
- Alpaca **live** or **paper** accounts
- Risk limits: max notional per order, max shares per position
- Kill switch file (`.kill_switch`) to halt new orders
- Extra live guard: orders only submit when `LIVE_TRADING_CONFIRMED=yes`
- **Backtesting** on Alpaca historical data or a local CSV
- **TradingView-style chart** (candlesticks, volume, SMAs, buy/sell markers)
- CLI: `status`, `run-once`, `run`, `backtest`, `chart`, `kill-switch`

## Screenshots

### Chart UI

Candlesticks, volume, SMA overlays, and buy/sell markers (Toyota `7203.T`, Japan TSE).

![Chart UI — Toyota 7203.T with SMAs and trade markers](docs/screenshots/chart.png)

### Backtest — compare all strategies

Equity curves and strategy comparison table for the same symbol and date range.

![Backtest — strategy comparison and equity curves](docs/screenshots/backtest.png)

## Quick start

### 1. Alpaca account

1. Sign up at [https://alpaca.markets/](https://alpaca.markets/)
2. Create API keys (live and/or paper)
3. For learning, use paper first: `TRADING_MODE=paper` and `ALPACA_BASE_URL=https://paper-api.alpaca.markets`

### 2. Install

```bash
cd ~/Projects/stock-auto-trader
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env with your API keys
```

### 3. Check status (no orders)

```bash
stock-trader status
```

### 4. Dry run one tick

With live keys but `LIVE_TRADING_CONFIRMED=no`, `run-once` evaluates signals but does **not** send orders:

```bash
stock-trader run-once
```

### 5. Enable live orders (careful)

Only after you understand the risks:

```env
TRADING_MODE=live
ALPACA_BASE_URL=https://api.alpaca.markets
LIVE_TRADING_CONFIRMED=yes
```

Then:

```bash
stock-trader run-once   # single evaluation
stock-trader run        # continuous loop (Ctrl+C to stop)
```

### Backtest page

```bash
stock-trader chart
# → http://127.0.0.1:8765/backtest
```

Pick **Japan (TSE)** or **United States**, symbol, date range, and a **strategy** (or **Compare all**). Japan uses Yahoo Finance (`.T` tickers); US uses Alpaca. Metrics include return, max drawdown, win rate, Sharpe, profit factor, and exposure.

**Strategies (single-symbol backtest):**

| ID | Description |
|----|-------------|
| `sma_crossover` | Fast/slow SMA cross from `.env` |
| `ma_cross_20_50` | Golden cross 20/50 + MA200 + filters (often strongest) |
| `ma_trend_20_50` | Golden/death cross above MA200 with volume |
| `rsi_mean_reversion` | RSI<30 above MA200; 5% stop, 10-day max hold |
| `breakout_20` | 20-day high breakout + volume; trailing stop |
| `trend_risk_control` | Beginner combo: trend + RSI + volume + stops |

Pair trading and multi-factor ranking are listed but need two symbols / a stock universe (not run in this UI yet).

CLI examples:

```bash
stock-trader backtest --market jp --symbol 6758.T --strategy ma_trend_20_50
stock-trader backtest --market jp --symbol 6758.T --compare

# All strategies × multiple symbols
stock-trader backtest-scan --symbols 6758.T,7203.T,SPY,AAPL
```

On the backtest page: enter **any** symbol, **Compare all** for one ticker, or **Scan presets** for all Japan/US picks in the toolbar.

### Chart UI (TradingView-style)

Starts a local web app with candlesticks, volume, SMA overlays, and crossover markers:

```bash
stock-trader chart
# → http://127.0.0.1:8765/
```

Use the toolbar to change symbol and date range. Enable **Live** to auto-refresh (default every 15s; latest quote/bar every ~7s). Set `CHART_REFRESH_SECONDS` in `.env` to change the interval.

For intraday movement, set `BAR_TIMEFRAME=5Min` or `1Min` in `.env` and restart the chart server.

The sidebar shows account info, backtest stats for the range, and simulated trades.

Built with [Lightweight Charts](https://www.tradingview.com/lightweight-charts/) (TradingView’s open-source library).

### Backtest

Run the SMA strategy on historical daily bars (no orders placed):

```bash
# Last 2 years (default) for SYMBOL in .env
stock-trader backtest

# Custom range
stock-trader backtest --start 2022-01-01 --end 2024-12-31 --symbol SPY

# Local CSV (timestamp/date + open,high,low,close,volume)
stock-trader backtest --csv ./data/spy.csv --start 2020-01-01 --end 2024-01-01
```

Reports strategy return vs buy-and-hold, max drawdown, trade count, win rate, and annualized Sharpe.

Fills are simulated at the **bar close** when a crossover fires, using the same position limits as live trading.

### Kill switch

```bash
stock-trader kill-switch --enable   # block new orders
stock-trader kill-switch --disable
```

## Configuration

| Variable | Description |
|----------|-------------|
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | API credentials |
| `ALPACA_BASE_URL` | Must match `TRADING_MODE` |
| `TRADING_MODE` | `live` or `paper` |
| `LIVE_TRADING_CONFIRMED` | `yes` to submit live orders |
| `SYMBOL` | Ticker, e.g. `SPY` |
| `FAST_SMA_PERIOD` / `SLOW_SMA_PERIOD` | Crossover windows |
| `MAX_ORDER_NOTIONAL` | Cap $ per buy order |
| `MAX_POSITION_SHARES` | Cap shares held / sold |
| `POLL_INTERVAL_SECONDS` | Delay between loop ticks |
| `BACKTEST_INITIAL_CASH` | Starting cash for US backtest (and CSV) |
| `BACKTEST_INITIAL_CASH_JPY` | Optional starting cash in yen for Japan backtest |
| `BACKTEST_MAX_ORDER_NOTIONAL_JPY` | Optional per-buy cap in yen (default scales from US-style `.env`) |

## US vs Japan stocks

| | **US (e.g. SPY, AAPL)** | **Japan (e.g. 7203.T)** |
|--|--|--|
| **What is SPY?** | An ETF that tracks the US S&P 500 index — a common US benchmark | N/A |
| **Data** | Alpaca (your API keys) | Yahoo Finance (free, ticker ends in `.T`) |
| **Auto-trading** | Yes (Alpaca paper/live) | No — chart & backtest only |
| **Symbol format** | `AAPL`, `SPY` | `7203.T` or `7203` (Toyota) |

Set Japan as default in `.env`:

```env
MARKET=jp
SYMBOL=7203.T
```

Popular Japan presets in the chart UI: Toyota, Sony, SoftBank, MUFG, Nintendo, and more.

## Currency (USD / JPY)

In the chart toolbar, choose **USD ($)**, **JPY (¥)**, or **Auto** (JPY for Japan stocks, USD for US).

Cross-market viewing converts prices using the live **USD/JPY** rate (`USDJPY=X` on Yahoo). Override in `.env`:

```env
DISPLAY_CURRENCY=auto
FX_USDJPY=150.0
```

## Strategy

- **Buy** when fast SMA crosses above slow SMA (and flat or short)
- **Sell** when fast SMA crosses below slow SMA (and long)
- Uses latest **daily** bars by default (`BAR_TIMEFRAME=1Day`)

## Disclaimer

You are responsible for compliance, taxes, and losses. Past performance of a simple SMA strategy does not predict future results.
