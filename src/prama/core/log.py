"""Structured logging with correlation and redaction.

Two properties matter more than formatting:

* **Correlation.** A single control execution touches the scheduler, a worker,
  a connector and the evidence ledger. Without a correlation id the log of a
  failure is a jigsaw. The id is carried in a ``ContextVar`` so it survives
  async hops without being threaded through every signature.
* **Redaction.** Logs are exported to a SIEM (NFR-SEC-011) and are read by
  people with less access than the process that wrote them. A value that must be
  masked in the UI must be masked here too, and the safest way to guarantee that
  is a filter on the handler rather than discipline at every call site.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar
from typing import Any, Final

from prama.core import pjson

correlation_id: ContextVar[str | None] = ContextVar("prama_correlation_id", default=None)
tenant_id: ContextVar[str | None] = ContextVar("prama_tenant_id", default=None)

REDACTED: Final[str] = "***"

#: Keys whose values never appear in a log record, whatever their content.
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "private_key",
        "session_secret",
        "client_secret",
        "credential",
        "credentials",
        "sas_token",
        "access_key",
    }
)

_SENSITIVE_TEXT = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|private[_-]?key)"
    r"\s*[:=]\s*(\"[^\"]*\"|'[^']*'|\S+)"
)


class RedactionFilter(logging.Filter):
    """Masks sensitive values in both the message and the structured extras."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SENSITIVE_TEXT.sub(lambda m: f"{m.group(1)}={REDACTED}", record.msg)
        fields = getattr(record, "prama_fields", None)
        if isinstance(fields, dict):
            record.prama_fields = redact_mapping(fields)
        return True


def redact_mapping(values: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask values whose key is sensitive."""
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key.lower() in SENSITIVE_KEYS:
            out[key] = REDACTED if value not in (None, "") else value
        elif isinstance(value, dict):
            out[key] = redact_mapping(value)
        else:
            out[key] = value
    return out


class ContextFilter(logging.Filter):
    """Attaches the ambient correlation and tenant ids to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get()
        record.tenant_id = tenant_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line — the format a log shipper wants."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        cid = getattr(record, "correlation_id", None)
        if cid:
            payload["correlation_id"] = cid
        tid = getattr(record, "tenant_id", None)
        if tid:
            payload["tenant_id"] = tid
        fields = getattr(record, "prama_fields", None)
        if isinstance(fields, dict) and fields:
            payload["fields"] = fields
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return pjson.dumps(payload)


class TextFormatter(logging.Formatter):
    """Human-readable format for a terminal."""

    DEFAULT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"

    def __init__(self) -> None:
        super().__init__(self.DEFAULT, datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        cid = getattr(record, "correlation_id", None)
        fields = getattr(record, "prama_fields", None)
        suffix = []
        if cid:
            suffix.append(f"cid={cid}")
        if isinstance(fields, dict) and fields:
            suffix.extend(f"{k}={v!r}" for k, v in sorted(fields.items()))
        return f"{base} [{' '.join(suffix)}]" if suffix else base


class LoggingConfigurator:
    """Installs Prama's logging configuration on the root logger.

    Idempotent: calling it twice replaces the handler rather than adding a
    second one, which is the usual cause of duplicated log lines in a reloading
    dev server.
    """

    _HANDLER_NAME = "prama"

    def __init__(self, *, level: str = "INFO", fmt: str = "text", stream: Any = None) -> None:
        self._level = level.upper()
        self._format = fmt.lower()
        self._stream = stream or sys.stderr

    def apply(self) -> None:
        root = logging.getLogger()
        for existing in list(root.handlers):
            if getattr(existing, "name", None) == self._HANDLER_NAME:
                root.removeHandler(existing)
        handler = logging.StreamHandler(self._stream)
        handler.name = self._HANDLER_NAME
        handler.setFormatter(JsonFormatter() if self._format == "json" else TextFormatter())
        handler.addFilter(ContextFilter())
        handler.addFilter(RedactionFilter())
        root.addHandler(handler)
        root.setLevel(self._level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_fields(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Emit a record carrying structured fields.

    ``logger.info("x", extra={"prama_fields": {...}})`` is the underlying form;
    this wrapper exists so call sites do not have to remember the key.
    """
    logger.log(level, message, extra={"prama_fields": fields})
