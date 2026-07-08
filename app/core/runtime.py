"""Process-wide runtime holder.

`create_app()` resolves settings once and stores them here so the API routers
(which are plain modules, not closures) can read the active configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings


@dataclass
class Runtime:
    settings: Settings
    demo_mode: bool


_runtime: Runtime | None = None


def set_runtime(runtime: Runtime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError("Runtime not initialized; create_app() must run first.")
    return _runtime
