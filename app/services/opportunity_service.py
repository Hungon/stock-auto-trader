"""Opportunity Finder service: scanning and per-symbol signal scoring."""

from __future__ import annotations

from app.opportunity.engine import (
    SETUP_TYPES,
    OpportunitySignal,
    compute_opportunity_signal,
    compute_opportunity_signal_at_index,
    signal_to_dict,
)
from app.opportunity.scan import scan_opportunities

__all__ = [
    "SETUP_TYPES",
    "OpportunitySignal",
    "compute_opportunity_signal",
    "compute_opportunity_signal_at_index",
    "signal_to_dict",
    "scan_opportunities",
]
