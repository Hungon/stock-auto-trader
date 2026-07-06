"""Opportunity Finder: deterministic multi-signal stock scanner.

Reuses the same indicator engine as the backtester (`strategy.indicators`) so the
scanner and backtests stay consistent. See `engine.py` for scoring/classification
and `scan.py` for universe scanning.
"""

from stock_auto_trader.opportunity.engine import (
    OpportunitySignal,
    compute_opportunity_signal,
    signal_to_dict,
)
from stock_auto_trader.opportunity.scan import scan_opportunities

__all__ = [
    "OpportunitySignal",
    "compute_opportunity_signal",
    "signal_to_dict",
    "scan_opportunities",
]
