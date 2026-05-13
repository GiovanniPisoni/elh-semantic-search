"""
Logging setup for the ELH RAG system.

Configures a single root logger with up to two handlers:
- A stream handler on stdout.
- A rotating file handler emitting one JSON object per line (JSON Lines).

The JSON format preserves all fields passed via ``logger.info(msg, extra={...})``
so tools can emit structured events such as::

    logger.info(
        "tool_executed",
        extra={
            "tool_name": "find_rooms",
            "duration_ms": 42,
            "result_count": 5,
            "warnings": [],
        },
    )
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from elh_rag.config import settings

_TEXT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s"
_TEXT_DATEFMT = "%H:%M:%S"


_LOG_RECORD_BUILTIN_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JSONFormatter(logging.Formatter):
    """Format LogRecord instances as single-line JSON objects (JSON Lines).

    Output schema (one event per line)::

        {
          "timestamp": "2026-05-14T10:32:14.123456+00:00",
          "level": "INFO",
          "logger": "elh_rag.tools.find_rooms",
          "message": "tool_executed",
          "module": "_sql_builder",
          "function": "_summarize_query",
          "line": 134,
          "tool_name": "find_rooms",       # any extra fields
          "duration_ms": 42,                # are passed through
          "exception": "Traceback ..."      # present only on exc_info
        }
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()

        payload: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_BUILTIN_ATTRS:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger for the entire application."""
    log_level = (level or settings.log_level).upper()

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)

    # Stream handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter(_TEXT_FORMAT, datefmt=_TEXT_DATEFMT))
    root.addHandler(stream_handler)

    # File handler
    if settings.log_file_path is not None:
        log_path = Path(settings.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=settings.log_file_max_bytes,
            backupCount=settings.log_file_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter())
        root.addHandler(file_handler)

    for noisy in ("httpx", "urllib3", "sentence_transformers", "pinecone"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
