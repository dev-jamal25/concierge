"""Structured JSON logger with redaction-aware filter (T040).

`configure_logging()` installs a JSON formatter and a redaction filter on the
`concierge` logger namespace. The redactor is a pluggable callable; T035's
`PIIRedactionMiddleware` swaps in a guardrails-backed implementation at app
startup. Until then the filter is a no-op so log lines emit unchanged.

The log level is read from `Settings.log_level` (env: `LOG_LEVEL`, default INFO).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.frameworks.config import Settings, get_settings

Redactor = Callable[[str], str]

CONCIERGE_LOGGER = "concierge"

_STANDARD_RECORD_FIELDS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }
)


class RedactionFilter(logging.Filter):
    """Runs the configured redactor over the formatted message before emission."""

    def __init__(self, redactor: Redactor | None = None) -> None:
        super().__init__()
        self._redactor: Redactor = redactor or (lambda s: s)

    def set_redactor(self, redactor: Redactor) -> None:
        self._redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        redacted = self._redactor(rendered)
        if redacted != rendered:
            record.msg = redacted
            record.args = None
        return True


class JsonFormatter(logging.Formatter):
    """Emits one JSON object per record on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


_redaction_filter = RedactionFilter()


def get_redaction_filter() -> RedactionFilter:
    """Return the singleton filter so T035 can swap in its redactor."""
    return _redaction_filter


def configure_logging(settings: Settings | None = None) -> None:
    """Idempotent setup of the `concierge` logger with JSON + redaction."""
    settings = settings or get_settings()
    logger = logging.getLogger(CONCIERGE_LOGGER)
    logger.setLevel(settings.log_level.upper())
    logger.propagate = False

    for existing in list(logger.handlers):
        logger.removeHandler(existing)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_redaction_filter)
    logger.addHandler(handler)
