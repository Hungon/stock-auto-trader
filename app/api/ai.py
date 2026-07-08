"""AI Opportunity Perspective API.

Returns a natural-language explanation of a symbol's computed signals. This
build uses a deterministic template generator (no LLM/secret); the pro build
swaps in a real provider behind the same contract.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.core.runtime import get_runtime
from app.services import ai_perspective_service as ai

router = APIRouter()


@router.post("/api/ai/opportunity-perspective")
def api_ai_perspective(body: dict = Body(...)) -> dict:
    rt = get_runtime()
    market = (body.get("market") or "jp").strip().lower()
    symbol = (body.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(400, "symbol required")
    try:
        return ai.generate_perspective(
            rt.settings,
            market=market,
            symbol=symbol,
            name=body.get("company_name"),
            demo_mode=rt.demo_mode,
        )
    except Exception as exc:
        raise HTTPException(502, f"Perspective failed: {exc}") from exc
