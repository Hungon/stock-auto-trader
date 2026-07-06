# AGENTS.md

## Cursor Cloud specific instructions

`stock-auto-trader` is a single Python (>=3.11) application: an Alpaca SMA-crossover
auto-trader plus a local FastAPI web UI for TradingView-style charting and
multi-strategy backtesting (US via Alpaca, Japan/TSE via yfinance). There is no
database, cache, or queue — state is local JSON/CSV files.

### Environment
- Dependencies live in a virtualenv at `.venv/` (the update script creates it and
  runs `pip install -e .` + `pip install pytest`). Activate it before any command:
  `source .venv/bin/activate`.
- `pytest` is intentionally NOT a declared dependency in `pyproject.toml`; the update
  script installs it separately.
- `.env` is created from `.env.example` during setup. It ships with placeholder
  Alpaca keys, which is fine for the credential-free paths below.

### Running / testing (standard commands live in `README.md` and `pyproject.toml`)
- Tests: `pytest` from the repo root (no pytest config file; no lint tooling is configured).
- Web UI: `stock-trader chart` serves the chart (`/`) and backtest (`/backtest`) pages
  plus `/api/*` on `http://127.0.0.1:8765`.
- CLI backtest example: `stock-trader backtest --market jp --symbol 7203.T --compare`.

### Non-obvious gotchas
- US symbols (e.g. `SPY`, `AAPL`) hit the real Alpaca API and will fail with `401`/`502`
  unless valid `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` are set in `.env`. For
  credential-free end-to-end testing, use **Japan/TSE symbols** (e.g. `7203.T`, `6758.T`)
  which use yfinance and need no keys.
- yfinance (Japan data + `USDJPY=X` FX) requires outbound network access to Yahoo
  Finance; it works in this environment.
- The web UI defaults to US/`SPY` on load, so the chart is blank until you switch the
  market to Japan (or add Alpaca keys). This is expected, not a bug.
