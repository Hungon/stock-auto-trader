"""Persisted equity snapshots for daily loss and drawdown tracking."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass
class RiskState:
    """Daily and peak equity written to ``RISK_STATE_PATH``."""

    date: str
    starting_equity: float
    peak_equity: float
    last_equity: float
    updated_at: str

    @classmethod
    def fresh(cls, equity: float, *, today: date | None = None) -> RiskState:
        d = today or date.today()
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            date=d.isoformat(),
            starting_equity=equity,
            peak_equity=equity,
            last_equity=equity,
            updated_at=now,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RiskState:
        return cls(
            date=str(data["date"]),
            starting_equity=float(data["starting_equity"]),
            peak_equity=float(data["peak_equity"]),
            last_equity=float(data.get("last_equity", data["starting_equity"])),
            updated_at=str(data.get("updated_at", "")),
        )


def load_risk_state(path: Path) -> RiskState | None:
    """Read risk state from disk; return None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return RiskState.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_risk_state(path: Path, state: RiskState) -> None:
    """Write risk state JSON, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n")


def update_risk_state(
    path: Path,
    current_equity: float,
    *,
    today: date | None = None,
) -> RiskState:
    """Update persisted state; reset daily starting equity on a new calendar day."""
    d = today or date.today()
    today_str = d.isoformat()
    existing = load_risk_state(path)

    if existing is None or existing.date != today_str:
        state = RiskState.fresh(current_equity, today=d)
    else:
        state = existing
        state.last_equity = current_equity
        state.peak_equity = max(state.peak_equity, current_equity)

    save_risk_state(path, state)
    return state
