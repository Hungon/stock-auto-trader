from __future__ import annotations

# US ticker -> Tokyo (.T) for the same company
US_TO_JP_TICKER: dict[str, str] = {
    "SONY": "6758.T",
    "TM": "7203.T",
    "TOYOTA": "7203.T",
    "HMC": "7267.T",
    "HONDA": "7267.T",
    "NTT": "9432.T",
    "NINTENDO": "7974.T",
    "NTDOY": "7974.T",
}

JP_TO_US_TICKER: dict[str, str] = {v: k for k, v in US_TO_JP_TICKER.items() if k != "TOYOTA"}


def map_symbol_for_market(symbol: str, market: str) -> tuple[str, str | None]:
    """
    Return (resolved_symbol, note) for user-facing alias messages.
    market is 'jp' or 'us'.
    """
    s = symbol.strip().upper()
    if market == "jp" and s in US_TO_JP_TICKER:
        mapped = US_TO_JP_TICKER[s]
        return mapped, f"{s} is the US ticker; using Tokyo listing {mapped} for yen prices."
    if market == "us" and s.endswith(".T") and s in {v for v in US_TO_JP_TICKER.values()}:
        for us_sym, jp_sym in US_TO_JP_TICKER.items():
            if jp_sym == s:
                return us_sym, f"{s} is Tokyo; using US listing {us_sym} for USD prices."
    return s, None
