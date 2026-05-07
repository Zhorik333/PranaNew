"""Admin schedule settings helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from bot.i18n import t
from bot.repositories.settings import SettingsRepository

ACTIVE_DATE_KEY = "active_date"
SCHEDULE_START_KEY = "schedule_start_at"
SCHEDULE_END_KEY = "schedule_end_at"
SCHEDULE_STEP_KEY = "schedule_step_minutes"
SCHEDULE_CAPACITY_KEY = "schedule_capacity"
DEFAULT_SCHEDULE_START = time(14, 0)
DEFAULT_SCHEDULE_END = time(19, 0)
DEFAULT_SCHEDULE_STEP = 10
DEFAULT_SCHEDULE_CAPACITY = 1


class AdminScheduleError(ValueError):
    """Raised when an admin schedule command is invalid."""


@dataclass(frozen=True)
class ScheduleSettings:
    """Current admin schedule settings."""

    active_date: date | None
    start_at: time
    end_at: time
    step_minutes: int
    capacity: int


def parse_set_active_date_command(text: str) -> date:
    """Parse /set_active_date YYYY-MM-DD."""

    parts = text.split()
    if len(parts) != 2:
        raise AdminScheduleError("invalid_active_date")
    try:
        return date.fromisoformat(parts[1])
    except ValueError as exc:
        raise AdminScheduleError("invalid_active_date") from exc


def parse_set_schedule_command(text: str) -> tuple[time, time, int, int]:
    """Parse /set_schedule START END STEP CAPACITY."""

    parts = text.split()
    if len(parts) != 5:
        raise AdminScheduleError("invalid_schedule")
    try:
        start_at = time.fromisoformat(parts[1])
        end_at = time.fromisoformat(parts[2])
        step_minutes = int(parts[3])
        capacity = int(parts[4])
    except ValueError as exc:
        raise AdminScheduleError("invalid_schedule") from exc
    _validate_schedule(start_at=start_at, end_at=end_at, step_minutes=step_minutes, capacity=capacity)
    return start_at, end_at, step_minutes, capacity


def _validate_schedule(*, start_at: time, end_at: time, step_minutes: int, capacity: int) -> None:
    if end_at < start_at or step_minutes <= 0 or capacity <= 0:
        raise AdminScheduleError("invalid_schedule")


def _parse_date_setting(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AdminScheduleError("invalid_stored_active_date") from exc


def _parse_time_setting(value: str | None, default: time) -> time:
    if not value:
        return default
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise AdminScheduleError("invalid_stored_schedule") from exc


def _parse_int_setting(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise AdminScheduleError("invalid_stored_schedule") from exc


def format_active_date_report(active_date: date | None, *, language: str) -> str:
    """Format the active date status."""

    if active_date is None:
        return t("admin_active_date_not_set", language)
    return t("admin_active_date_current", language, active_date=active_date.isoformat())


def format_schedule_settings_report(settings: ScheduleSettings, *, language: str) -> str:
    """Format all current schedule settings."""

    active_date = settings.active_date.isoformat() if settings.active_date else "—"
    return "\n".join(
        [
            t("admin_schedule_settings_title", language),
            f"Активная дата: {active_date}",
            f"Время: {settings.start_at:%H:%M}-{settings.end_at:%H:%M}",
            f"Шаг: {settings.step_minutes}",
            f"Capacity: {settings.capacity}",
        ]
    )


class AdminScheduleService:
    """Application service for admin schedule settings."""

    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def set_active_date(self, active_date: date) -> None:
        async with self.db_pool.acquire() as connection:
            await SettingsRepository(connection).set(ACTIVE_DATE_KEY, active_date.isoformat())

    async def get_active_date(self) -> date | None:
        async with self.db_pool.acquire() as connection:
            value = await SettingsRepository(connection).get(ACTIVE_DATE_KEY)
        return _parse_date_setting(value)

    async def clear_active_date(self) -> None:
        async with self.db_pool.acquire() as connection:
            await SettingsRepository(connection).delete(ACTIVE_DATE_KEY)

    async def set_schedule(self, *, start_at: time, end_at: time, step_minutes: int, capacity: int) -> None:
        _validate_schedule(start_at=start_at, end_at=end_at, step_minutes=step_minutes, capacity=capacity)
        async with self.db_pool.acquire() as connection:
            repository = SettingsRepository(connection)
            await repository.set(SCHEDULE_START_KEY, start_at.strftime("%H:%M"))
            await repository.set(SCHEDULE_END_KEY, end_at.strftime("%H:%M"))
            await repository.set(SCHEDULE_STEP_KEY, str(step_minutes))
            await repository.set(SCHEDULE_CAPACITY_KEY, str(capacity))

    async def get_schedule_settings(self) -> ScheduleSettings:
        async with self.db_pool.acquire() as connection:
            repository = SettingsRepository(connection)
            active_date_raw = await repository.get(ACTIVE_DATE_KEY)
            start_raw = await repository.get(SCHEDULE_START_KEY)
            end_raw = await repository.get(SCHEDULE_END_KEY)
            step_raw = await repository.get(SCHEDULE_STEP_KEY)
            capacity_raw = await repository.get(SCHEDULE_CAPACITY_KEY)
        settings = ScheduleSettings(
            active_date=_parse_date_setting(active_date_raw),
            start_at=_parse_time_setting(start_raw, DEFAULT_SCHEDULE_START),
            end_at=_parse_time_setting(end_raw, DEFAULT_SCHEDULE_END),
            step_minutes=_parse_int_setting(step_raw, DEFAULT_SCHEDULE_STEP),
            capacity=_parse_int_setting(capacity_raw, DEFAULT_SCHEDULE_CAPACITY),
        )
        _validate_schedule(
            start_at=settings.start_at,
            end_at=settings.end_at,
            step_minutes=settings.step_minutes,
            capacity=settings.capacity,
        )
        return settings
