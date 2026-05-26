"""Unit tests for structured JSON logger (T040)."""

from __future__ import annotations

import io
import json
import logging

import pytest

from app.frameworks.observability.logging import (
    CONCIERGE_LOGGER,
    JsonFormatter,
    RedactionFilter,
    configure_logging,
    get_redaction_filter,
)


def _emit(level: str = "INFO") -> tuple[logging.Logger, io.StringIO]:
    """Build a logger wired to an in-memory stream for inspection."""
    logger = logging.getLogger(f"{CONCIERGE_LOGGER}.test")
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger, stream


def test_json_formatter_emits_required_fields() -> None:
    logger, stream = _emit()
    logger.info("hello %s", "world")
    payload = json.loads(stream.getvalue())
    assert payload["level"] == "INFO"
    assert payload["logger"] == "concierge.test"
    assert payload["message"] == "hello world"
    assert "ts" in payload


def test_json_formatter_includes_extra_fields() -> None:
    logger, stream = _emit()
    logger.info("provisioned", extra={"tenant_id": "abc", "duration_ms": 12})
    payload = json.loads(stream.getvalue())
    assert payload["tenant_id"] == "abc"
    assert payload["duration_ms"] == 12


def test_redaction_filter_is_passthrough_by_default() -> None:
    logger, stream = _emit()
    logger.addFilter(RedactionFilter())
    logger.info("plain message")
    assert json.loads(stream.getvalue())["message"] == "plain message"


def test_redaction_filter_runs_redactor() -> None:
    logger, stream = _emit()
    logger.addFilter(RedactionFilter(redactor=lambda s: s.replace("4242", "[REDACTED]")))
    logger.info("card 4242")
    assert json.loads(stream.getvalue())["message"] == "card [REDACTED]"


def test_configure_logging_sets_level_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.frameworks import config

    monkeypatch.setattr(config, "get_settings", lambda: config.Settings(log_level="DEBUG"))
    from app.frameworks.observability import logging as obs_logging

    monkeypatch.setattr(obs_logging, "get_settings", config.get_settings)

    configure_logging()
    logger = logging.getLogger(CONCIERGE_LOGGER)
    try:
        assert logger.level == logging.DEBUG
        assert any(get_redaction_filter() in h.filters for h in logger.handlers)
    finally:
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)
