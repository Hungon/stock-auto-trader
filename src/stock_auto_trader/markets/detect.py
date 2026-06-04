from __future__ import annotations

import re

_JP_SUFFIX = re.compile(r"\.T$", re.IGNORECASE)
_JP_CODE = re.compile(r"^\d{4}$")


def is_japan_symbol(symbol: str) -> bool:
    s = symbol.strip().upper()
    return bool(_JP_SUFFIX.search(s) or _JP_CODE.match(s))


def normalize_symbol(symbol: str, market: str | None = None) -> str:
    """Return Yahoo/Alpaca ticker (e.g. 7203 -> 7203.T for Japan)."""
    s = symbol.strip().upper()
    if _JP_SUFFIX.search(s):
        return s
    if market == "jp" or (market != "us" and _JP_CODE.match(s)):
        return f"{s}.T"
    return s
