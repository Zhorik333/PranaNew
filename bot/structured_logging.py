"""Structured JSON logging helpers with secret redaction."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import logging
import re
import sys
from typing import Any

SENSITIVE_KEYS = {
    "bot_token",
    "database_url",
    "dsn",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
}
REDACTED = "[REDACTED]"
TELEGRAM_CREDENTIAL_RE = re.compile(
    r"\b"
    r"\d{6,12}"
    r":"
    r"[A-Za-z0-9_-]{10,}"
    r"\b"
)
DATABASE_URL_PATTERN = re.compile(r"postgres(?:ql)?://[^\s'\")]+", re.IGNORECASE)


class JsonLogFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": sanitize_value(getattr(record, "event", record.getMessage())),
            "message": sanitize_value(record.getMessage()),
        }
        context = getattr(record, "context", None)
        if isinstance(context, Mapping):
            payload.update(sanitize_context(context))
        if record.exc_info:
            payload["exception"] = sanitize_value(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_structured_logging(
    *,
    level: str | int = "INFO",
    stream=None,
    logger_name: str = "prananew",
) -> logging.Logger:
    """Configure and return a structured logger for application events."""

    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.setLevel(_normalize_log_level(level))
    logger.propagate = False
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    return logger


def get_structured_logger(name: str = "prananew") -> logging.Logger:
    """Return a named structured logger without changing global configuration."""

    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    exc_info: bool | tuple[Any, Any, Any] | None = None,
    **context: Any,
) -> None:
    """Log a structured event with sanitized context."""

    logger.log(
        level,
        event,
        extra={"event": event, "context": sanitize_context(context)},
        exc_info=exc_info,
    )


def sanitize_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return a sanitized copy of context suitable for logs."""

    return {key: sanitize_value(value, key=key) for key, value in context.items()}


def sanitize_value(value: Any, *, key: str | None = None) -> Any:
    """Redact known secrets from arbitrary values."""

    if key is not None and _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        return sanitize_context(value)
    if isinstance(value, (list, tuple)):
        return [sanitize_value(item) for item in value]
    if isinstance(value, (str, bytes)):
        text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        text = DATABASE_URL_PATTERN.sub(REDACTED, text)
        text = TELEGRAM_CREDENTIAL_RE.sub(REDACTED, text)
        return text
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in SENSITIVE_KEYS)


def _normalize_log_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    normalized = level.upper()
    value = getattr(logging, normalized, None)
    return value if isinstance(value, int) else logging.INFO
