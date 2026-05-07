"""Configuration helpers for the PranaNew Telegram booking bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
import os

from dotenv import dotenv_values


DEFAULT_ENV_PATH = Path(".env")
DEFAULT_LANGUAGE = "ru"
DEFAULT_TZ = "Europe/Belgrade"
DEFAULT_REVIEW_DELAY_MINUTES = 30
DEFAULT_LOG_LEVEL = "INFO"


class ConfigError(RuntimeError):
    """Raised when application configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Runtime settings loaded from environment variables or a .env file."""

    bot_token: str = field(repr=False)
    database_url: str
    admin_chat_id: int
    default_language: str = DEFAULT_LANGUAGE
    default_tz: str = DEFAULT_TZ
    review_delay_minutes: int = DEFAULT_REVIEW_DELAY_MINUTES
    log_level: str = DEFAULT_LOG_LEVEL


def load_config(env_path: str | Path = DEFAULT_ENV_PATH) -> Config:
    """Load validated application configuration.

    Real environment variables intentionally override values from the .env file,
    which makes local overrides and deployment environment settings predictable.
    """

    values = _load_env_values(Path(env_path))

    return Config(
        bot_token=_required(values, "BOT_TOKEN"),
        database_url=_required(values, "DATABASE_URL"),
        admin_chat_id=_required_int(values, "ADMIN_CHAT_ID"),
        default_language=_optional(values, "DEFAULT_LANGUAGE", DEFAULT_LANGUAGE),
        default_tz=_optional(values, "DEFAULT_TZ", DEFAULT_TZ),
        review_delay_minutes=_optional_int(
            values,
            "REVIEW_DELAY_MINUTES",
            DEFAULT_REVIEW_DELAY_MINUTES,
        ),
        log_level=_optional(values, "LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
    )


def _load_env_values(env_path: Path) -> dict[str, str]:
    file_values = {
        key: value
        for key, value in dotenv_values(env_path).items()
        if value is not None
    }
    merged = dict(file_values)
    merged.update(os.environ)
    return merged


def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ConfigError(f"Missing required setting: {key}")
    return value


def _optional(values: Mapping[str, str], key: str, default: str) -> str:
    value = values.get(key, "").strip()
    return value or default


def _required_int(values: Mapping[str, str], key: str) -> int:
    raw_value = _required(values, key)
    return _parse_int(raw_value, key)


def _optional_int(values: Mapping[str, str], key: str, default: int) -> int:
    raw_value = values.get(key, "").strip()
    if not raw_value:
        return default
    return _parse_int(raw_value, key)


def _parse_int(raw_value: str, key: str) -> int:
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer setting {key}: {raw_value!r}") from exc
