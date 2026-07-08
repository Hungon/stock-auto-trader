from __future__ import annotations

from app.currency import Currency, convert_amount


def _scale_point(point: dict, factor: float, keys: tuple[str, ...]) -> dict:
    out = dict(point)
    for key in keys:
        if key in out and out[key] is not None:
            out[key] = float(out[key]) * factor
    return out


def apply_currency_to_chart_payload(
    payload: dict,
    *,
    native: Currency,
    display: Currency,
    usdjpy: float,
) -> dict:
    native_close = None
    if payload.get("last"):
        native_close = float(payload["last"]["close"])

    if native == display:
        payload["native_currency"] = native
        payload["display_currency"] = display
        payload["fx_usdjpy"] = usdjpy
        payload["conversion_applied"] = False
        return payload

    if native == "usd" and display == "jpy":
        factor = usdjpy
    elif native == "jpy" and display == "usd":
        factor = 1.0 / usdjpy
    else:
        factor = 1.0

    payload["candles"] = [
        _scale_point(c, factor, ("open", "high", "low", "close")) for c in payload["candles"]
    ]
    payload["fast_sma"] = [
        _scale_point(p, factor, ("value",)) for p in payload["fast_sma"]
    ]
    payload["slow_sma"] = [
        _scale_point(p, factor, ("value",)) for p in payload["slow_sma"]
    ]
    if payload.get("last"):
        payload["last"] = _scale_point(payload["last"], factor, ("open", "high", "low", "close"))

    for trade in payload.get("trades", []):
        trade["price"] = convert_amount(
            float(trade["price"]),
            from_currency=native,
            to_currency=display,
            usdjpy=usdjpy,
        )

    if payload.get("stats"):
        for key in ("total_return_pct", "buy_hold_return_pct", "max_drawdown_pct"):
            pass  # percentages unchanged
        # initial/final equity not in stats dict currently

    payload["native_currency"] = native
    payload["display_currency"] = display
    payload["fx_usdjpy"] = usdjpy
    payload["currency_converted"] = True
    payload["conversion_applied"] = True
    payload["native_last_close"] = native_close
    return payload


def apply_currency_to_tick(tick: dict, *, native: Currency, display: Currency, usdjpy: float) -> dict:
    if native == display:
        tick["native_currency"] = native
        tick["display_currency"] = display
        tick["fx_usdjpy"] = usdjpy
        return tick

    bar = tick["bar"]
    quote = tick["quote"]
    for key in ("open", "high", "low", "close"):
        bar[key] = convert_amount(
            float(bar[key]), from_currency=native, to_currency=display, usdjpy=usdjpy
        )
    for key in ("bid", "ask"):
        quote[key] = convert_amount(
            float(quote[key]), from_currency=native, to_currency=display, usdjpy=usdjpy
        )
    tick["native_currency"] = native
    tick["display_currency"] = display
    tick["fx_usdjpy"] = usdjpy
    return tick
