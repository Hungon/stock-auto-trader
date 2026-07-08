"""Opportunity Finder: deterministic multi-signal stock scanner.

Reuses the same indicator engine as the backtester (`strategy.indicators`) so the
scanner and backtests stay consistent. See `engine.py` for scoring/classification
and `scan.py` for universe scanning.
"""

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
