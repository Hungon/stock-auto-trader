"""Structured logging for live trading and backtests.

Supports text (default) and JSON output via LOG_FORMAT. Secrets in log
extra fields are redacted automatically.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "secret_key",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
    }
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON with optional event fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "taskName",
                "message",
                "event",
            }:
                continue
            if key in _SECRET_KEYS or "secret" in key.lower() or "api_key" in key.lower():
                payload[key] = "[REDACTED]"
            else:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *config* with API keys and secrets replaced."""
    redacted: dict[str, Any] = {}
    for key, value in config.items():
        if key in _SECRET_KEYS or "secret" in key.lower() or key.endswith("_key"):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def setup_logging(settings: Settings, *, verbose: bool = False) -> None:
    """Configure root logger from Settings (format, level, optional file)."""
    level_name = settings.log_level.upper()
    if verbose:
        level_name = "DEBUG"
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    if settings.log_format == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    if settings.log_file:
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(settings.log_file)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Emit a structured log line; *event* is duplicated in JSON as ``event``."""
    extra = {"event": event, **fields}
    logger.log(level, event, extra=extra)
