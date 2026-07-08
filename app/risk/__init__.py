"""Live-trading risk checks and pre-order gating.

Submodules implement individual checks (daily loss, drawdown, stale data,
market hours). :class:`RiskGate` runs them in order before any order is sent.
"""
