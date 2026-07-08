"""Opportunity Finder API: scan a market universe and rank by signal."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.core.runtime import get_runtime
from app.services import opportunity_service as ops

router = APIRouter()


@router.get("/api/opportunities")
def api_opportunities(
    market: str | None = Query(None, description="us or jp"),
    symbols: str | None = Query(
        None, description="Optional comma-separated tickers to scan"
    ),
    start: str | None = Query(None, description="YYYY-MM-DD"),
    end: str | None = Query(None, description="YYYY-MM-DD"),
) -> dict:
    rt = get_runtime()
    settings = rt.settings
    mkt = (market or "jp").strip().lower()
    if mkt not in {"jp", "us"}:
        mkt = "jp"
    symbol_list = (
        [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    )
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except ValueError as exc:
        raise HTTPException(400, f"Invalid date: {exc}") from exc
    if start_date and end_date and start_date >= end_date:
        raise HTTPException(400, "start must be before end")
    try:
        return ops.scan_opportunities(
            settings,
            market=mkt,
            symbols=symbol_list,
            start=start_date,
            end=end_date,
            demo_mode=rt.demo_mode,
        )
    except Exception as exc:
        raise HTTPException(502, f"Opportunity scan failed: {exc}") from exc
