"""Formatting helpers for booking-related admin notifications."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from bot.i18n import t


def _value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)


def _optional_value(row: Any, key: str) -> Any:
    try:
        return _value(row, key)
    except (KeyError, AttributeError):
        return None


def _format_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)


def _client_label(details: Any) -> str:
    username = _optional_value(details, "username")
    if username:
        return f"@{username}"

    full_name = " ".join(
        part
        for part in (
            _optional_value(details, "first_name"),
            _optional_value(details, "last_name"),
        )
        if part
    ).strip()
    if full_name:
        return full_name
    return f"ID {int(_value(details, 'user_id'))}"


def format_admin_new_booking_message(details: Any, *, language: str) -> str:
    """Format a compact admin-group message for a newly confirmed booking."""

    booking_id = int(_value(details, "booking_id"))
    return "\n".join(
        [
            f"🆕 {t('admin_new_booking', language)}",
            f"Бронь: #{booking_id}",
            f"Клиент: {_client_label(details)}",
            f"Дата: {_format_date(_value(details, 'slot_date'))}",
            f"Слоты: {_value(details, 'slots_label')}",
            f"Выдача: {_format_time(_value(details, 'pickup_time'))}",
        ]
    )
