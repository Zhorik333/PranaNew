"""Admin analytics parsing, formatting, and service helpers."""

from __future__ import annotations

from datetime import date
from typing import Any

from bot.i18n import t
from bot.repositories.analytics import AnalyticsRepository


class AnalyticsError(ValueError):
    """Raised when analytics commands or reports cannot be handled."""


def parse_admin_analytics_command(text: str) -> date:
    """Parse /analytics YYYY-MM-DD."""

    parts = text.split()
    if len(parts) != 2:
        raise AnalyticsError("invalid_analytics_command")
    try:
        return date.fromisoformat(parts[1])
    except ValueError as exc:
        raise AnalyticsError("invalid_analytics_command") from exc


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)


def _int_value(row: Any, key: str) -> int:
    value = _row_value(row, key)
    return int(value or 0)


def format_admin_analytics_report(row: Any, *, language: str) -> str:
    """Format one daily analytics report for admins."""

    slot_date = _row_value(row, "slot_date")
    slot_date_text = slot_date.isoformat() if hasattr(slot_date, "isoformat") else str(slot_date)
    total_capacity = _int_value(row, "total_capacity")
    occupied_slots = _int_value(row, "occupied_slots")
    load_percent = round((occupied_slots / total_capacity) * 100) if total_capacity > 0 else 0
    return "\n".join(
        [
            t("admin_analytics_report_title", language, slot_date=slot_date_text),
            f"Показы свободных слотов: {_int_value(row, 'free_slots_views')}",
            f"Создано броней: {_int_value(row, 'created_bookings')}",
            f"Активные брони: {_int_value(row, 'active_bookings')}",
            f"Отмены: {_int_value(row, 'cancelled_bookings')}",
            f"Завершения: {_int_value(row, 'completed_bookings')}",
            f"Слоты: {_int_value(row, 'total_slots')}",
            f"Загрузка слотов: {occupied_slots}/{total_capacity} ({load_percent}%)",
        ]
    )


class AnalyticsService:
    """Application service for analytics tracking and admin reports."""

    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def record_free_slots_view(self, *, user_id: int | None = None) -> None:
        """Record a free-slots view without breaking the caller if analytics storage fails."""

        try:
            async with self.db_pool.acquire() as connection:
                await AnalyticsRepository(connection).record_free_slots_view(user_id=user_id)
        except Exception:
            return

    async def get_daily_report(self, *, slot_date: date) -> Any:
        """Return one daily analytics report row."""

        try:
            async with self.db_pool.acquire() as connection:
                row = await AnalyticsRepository(connection).get_daily_report(slot_date=slot_date)
        except Exception as exc:
            raise AnalyticsError("analytics_report_unavailable") from exc
        if row is None:
            raise AnalyticsError("analytics_report_unavailable")
        return row
