"""Tests for :mod:`elh_rag.logging_setup`."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from elh_rag.logging_setup import JSONFormatter, setup_logging

# JSONFormatter


def _make_record(
    msg: str = "hello",
    level: int = logging.INFO,
    name: str = "elh_rag.test",
    extra: dict | None = None,
) -> logging.LogRecord:
    """Build a LogRecord, optionally attaching extra attributes."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


def test_formatter_produces_valid_json() -> None:
    record = _make_record("hello")
    line = JSONFormatter().format(record)
    parsed = json.loads(line)
    assert parsed["message"] == "hello"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "elh_rag.test"
    assert parsed["line"] == 42
    # ISO 8601 with timezone
    assert parsed["timestamp"].endswith("+00:00")


def test_formatter_includes_extra_fields() -> None:
    record = _make_record(
        "tool_executed",
        extra={
            "tool_name": "find_rooms",
            "duration_ms": 42,
            "result_count": 5,
            "warnings": [],
        },
    )
    parsed = json.loads(JSONFormatter().format(record))
    assert parsed["tool_name"] == "find_rooms"
    assert parsed["duration_ms"] == 42
    assert parsed["result_count"] == 5
    assert parsed["warnings"] == []


def test_formatter_omits_builtin_log_attrs() -> None:
    """Builtin LogRecord attrs must not leak into the JSON output."""
    record = _make_record("hello")
    parsed = json.loads(JSONFormatter().format(record))
    # These are stdlib LogRecord internals we deliberately exclude:
    for forbidden in ("msg", "args", "msecs", "relativeCreated", "thread", "process"):
        assert forbidden not in parsed


def test_formatter_includes_exception_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="elh_rag.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=99,
        msg="failed",
        args=(),
        exc_info=exc_info,
    )
    parsed = json.loads(JSONFormatter().format(record))
    assert "exception" in parsed
    assert "ValueError: boom" in parsed["exception"]


def test_formatter_serialises_non_json_values_as_strings() -> None:
    """Datetimes, paths, etc. must not crash the formatter."""
    from datetime import datetime

    record = _make_record(
        "with_path",
        extra={"checked_at": datetime(2026, 5, 14, 10, 0), "src": Path("/tmp/x")},
    )
    parsed = json.loads(JSONFormatter().format(record))
    # Values became strings via default=str — no exception raised
    assert isinstance(parsed["checked_at"], str)
    assert isinstance(parsed["src"], str)


# setup_logging


def test_setup_logging_is_idempotent() -> None:
    """Calling setup_logging twice must not duplicate handlers."""
    setup_logging("INFO")
    root = logging.getLogger()
    first_count = len(root.handlers)
    setup_logging("INFO")
    second_count = len(root.handlers)
    assert first_count == second_count


def test_setup_logging_attaches_file_handler_when_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When settings.log_file_path is set, a rotating file handler is added."""
    from elh_rag import logging_setup
    from elh_rag.config import settings as live_settings

    log_path = tmp_path / "test.jsonl"
    monkeypatch.setattr(live_settings, "log_file_path", log_path)
    logging_setup.setup_logging("INFO")

    root = logging.getLogger()
    file_handlers = [
        h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert isinstance(file_handlers[0].formatter, JSONFormatter)

    # Smoke: emitting a record actually writes a parseable JSON line
    logger = logging.getLogger("elh_rag.test")
    logger.info("smoke_event", extra={"k": "v"})
    for h in file_handlers:
        h.flush()
    content = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert content, "expected at least one log line on disk"
    last = json.loads(content[-1])
    assert last["message"] == "smoke_event"
    assert last["k"] == "v"


def test_setup_logging_no_file_handler_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When settings.log_file_path is None, only the stream handler is attached."""
    import logging.handlers as lh

    from elh_rag import logging_setup
    from elh_rag.config import settings as live_settings

    monkeypatch.setattr(live_settings, "log_file_path", None)
    logging_setup.setup_logging("INFO")

    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, lh.RotatingFileHandler)]
    stream_handlers = [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, lh.RotatingFileHandler)
    ]
    assert file_handlers == []
    assert len(stream_handlers) == 1
