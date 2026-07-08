from __future__ import annotations

# Yahoo Finance tickers for Tokyo Stock Exchange (append .T)
JAPAN_STOCKS: list[dict[str, str]] = [
    {"symbol": "7203.T", "name": "Toyota Motor"},
    {"symbol": "6758.T", "name": "Sony Group"},
    {"symbol": "9984.T", "name": "SoftBank Group"},
    {"symbol": "8306.T", "name": "MUFG"},
    {"symbol": "7974.T", "name": "Nintendo"},
    {"symbol": "6861.T", "name": "Keyence"},
    {"symbol": "9432.T", "name": "NTT"},
    {"symbol": "6098.T", "name": "Recruit"},
    {"symbol": "4063.T", "name": "Shin-Etsu Chemical"},
    {"symbol": "8035.T", "name": "Tokyo Electron"},
]

US_STOCKS: list[dict[str, str]] = [
    {"symbol": "SPY", "name": "S&P 500 ETF (US market benchmark)"},
    {"symbol": "QQQ", "name": "Nasdaq 100 ETF"},
    {"symbol": "AAPL", "name": "Apple"},
    {"symbol": "MSFT", "name": "Microsoft"},
    {"symbol": "NVDA", "name": "NVIDIA"},
]
