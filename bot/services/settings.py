"""Validated application settings service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.repositories.settings import SettingsRepository

WORKING_START_TIME_KEY = "working_start_time"
WORKING_END_TIME_KEY = "working_end_time"
SLOT_STEP_KEY = "slot_step"
MAX_CONSECUTIVE_KEY = "max_consecutive"
TZ_KEY = "tz"
REVIEW_DELAY_MINUTES_KEY = "review_delay_minutes"

DEFAULT_WORKING_START_TIME = time(14, 0)
DEFAULT_WORKING_END_TIME = time(19, 0)
DEFAULT_SLOT_STEP = 10
DEFAULT_MAX_CONSECUTIVE = 5
DEFAULT_TZ = "Europe/Belgrade"
DEFAULT_REVIEW_DELAY_MINUTES = 30

SUPPORTED_SETTING_KEYS = {
    WORKING_START_TIME_KEY,
    WORKING_END_TIME_KEY,
    SLOT_STEP_KEY,
    MAX_CONSECUTIVE_KEY,
    TZ_KEY,
    REVIEW_DELAY_MINUTES_KEY,
}


class SettingsServiceError(ValueError):
    """Raised when a setting is missing, invalid, or unsupported."""


@dataclass(frozen=True)
class BotSettings:
    """Validated runtime settings used by booking and scheduler flows."""

    working_start_time: time
    working_end_time: time
    slot_step: int
    max_consecutive: int
    tz: str
    review_delay_minutes: int


class SettingsService:
    """Read and validate bot settings from the settings repository."""

    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def get_settings(self) -> BotSettings:
        """Return all bot settings, using safe defaults for missing values."""

        async with self.db_pool.acquire() as connection:
            repository = SettingsRepository(connection)
            raw_settings = await _fetch_raw_settings(repository)
        return _build_settings(raw_settings)

    async def set_setting(self, key: str, value: str) -> None:
        """Validate and persist one supported setting."""

        normalized_key = key.strip()
        normalized_value = value.strip()
        _validate_single_setting(normalized_key, normalized_value)
        async with self.db_pool.acquire() as connection:
            repository = SettingsRepository(connection)
            raw_settings = await _fetch_raw_settings(repository)
            raw_settings[normalized_key] = normalized_value
            _build_settings(raw_settings)
            await repository.set(normalized_key, normalized_value)


async def _fetch_raw_settings(repository: SettingsRepository) -> dict[str, str | None]:
    return {
        WORKING_START_TIME_KEY: await repository.get(WORKING_START_TIME_KEY),
        WORKING_END_TIME_KEY: await repository.get(WORKING_END_TIME_KEY),
        SLOT_STEP_KEY: await repository.get(SLOT_STEP_KEY),
        MAX_CONSECUTIVE_KEY: await repository.get(MAX_CONSECUTIVE_KEY),
        TZ_KEY: await repository.get(TZ_KEY),
        REVIEW_DELAY_MINUTES_KEY: await repository.get(REVIEW_DELAY_MINUTES_KEY),
    }


def _build_settings(raw_settings: dict[str, str | None]) -> BotSettings:
    settings = BotSettings(
        working_start_time=_parse_time_setting(raw_settings.get(WORKING_START_TIME_KEY), DEFAULT_WORKING_START_TIME),
        working_end_time=_parse_time_setting(raw_settings.get(WORKING_END_TIME_KEY), DEFAULT_WORKING_END_TIME),
        slot_step=_parse_positive_int_setting(raw_settings.get(SLOT_STEP_KEY), DEFAULT_SLOT_STEP),
        max_consecutive=_parse_positive_int_setting(raw_settings.get(MAX_CONSECUTIVE_KEY), DEFAULT_MAX_CONSECUTIVE),
        tz=_parse_timezone_setting(raw_settings.get(TZ_KEY), DEFAULT_TZ),
        review_delay_minutes=_parse_non_negative_int_setting(
            raw_settings.get(REVIEW_DELAY_MINUTES_KEY),
            DEFAULT_REVIEW_DELAY_MINUTES,
        ),
    )
    _validate_settings(settings)
    return settings


def _is_hh_mm(value: str) -> bool:
    return (
        len(value) == 5
        and value[0:2].isascii()
        and value[0:2].isdecimal()
        and value[2] == ":"
        and value[3:5].isascii()
        and value[3:5].isdecimal()
    )


def _parse_time_setting(value: str | None, default: time) -> time:
    if value is None:
        return default
    if not _is_hh_mm(value):
        raise SettingsServiceError("invalid_time_setting")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise SettingsServiceError("invalid_time_setting") from exc


def _parse_positive_int_setting(value: str | None, default: int) -> int:
    if value is None:
        return default
    if not value.isascii() or not value.isdecimal():
        raise SettingsServiceError("invalid_integer_setting")
    parsed = int(value)
    if parsed <= 0:
        raise SettingsServiceError("invalid_positive_integer_setting")
    return parsed


def _parse_non_negative_int_setting(value: str | None, default: int) -> int:
    if value is None:
        return default
    if not value.isascii() or not value.isdecimal():
        raise SettingsServiceError("invalid_integer_setting")
    parsed = int(value)
    if parsed < 0:
        raise SettingsServiceError("invalid_non_negative_integer_setting")
    return parsed


def _parse_timezone_setting(value: str | None, default: str) -> str:
    if value is None:
        return default
    parsed = value.strip()
    if not parsed:
        raise SettingsServiceError("invalid_timezone_setting")
    try:
        ZoneInfo(parsed)
    except ZoneInfoNotFoundError as exc:
        raise SettingsServiceError("invalid_timezone_setting") from exc
    return parsed


def _validate_settings(settings: BotSettings) -> None:
    if settings.working_end_time <= settings.working_start_time:
        raise SettingsServiceError("invalid_working_hours")


def _validate_single_setting(key: str, value: str) -> None:
    if key not in SUPPORTED_SETTING_KEYS:
        raise SettingsServiceError("unsupported_setting")
    if key in {WORKING_START_TIME_KEY, WORKING_END_TIME_KEY}:
        _parse_time_setting(value, DEFAULT_WORKING_START_TIME)
        return
    if key in {SLOT_STEP_KEY, MAX_CONSECUTIVE_KEY}:
        _parse_positive_int_setting(value, 1)
        return
    if key == REVIEW_DELAY_MINUTES_KEY:
        _parse_non_negative_int_setting(value, 0)
        return
    if key == TZ_KEY:
        _parse_timezone_setting(value, DEFAULT_TZ)
        return
    raise SettingsServiceError("unsupported_setting")
