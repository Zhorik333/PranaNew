"""Admin booking management parsing, formatting, and service helpers."""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from bot.i18n import t
from bot.repositories.bookings import BookingsRepository

ADMIN_BOOKING_STATUSES = {"active", "completed", "cancelled"}
ADMIN_BOOKING_TARGET_STATUSES = {"completed", "cancelled"}


class AdminBookingError(ValueError):
    """Raised when an admin booking command or transition is invalid."""


def parse_admin_bookings_command(text: str) -> tuple[date, str | None]:
    """Parse /bookings DATE [active|completed|cancelled|all]."""

    parts = text.split()
    if len(parts) not in {2, 3}:
        raise AdminBookingError("invalid_bookings_command")
    try:
        slot_date = date.fromisoformat(parts[1])
    except ValueError as exc:
        raise AdminBookingError("invalid_bookings_command") from exc
    status = None
    if len(parts) == 3:
        requested_status = parts[2].lower()
        if requested_status != "all":
            if requested_status not in ADMIN_BOOKING_STATUSES:
                raise AdminBookingError("invalid_status")
            status = requested_status
    return slot_date, status


def parse_admin_booking_detail_command(text: str) -> int:
    """Parse /booking ID."""

    parts = text.split()
    if len(parts) != 2:
        raise AdminBookingError("invalid_booking_id")
    try:
        booking_id = int(parts[1])
    except ValueError as exc:
        raise AdminBookingError("invalid_booking_id") from exc
    if booking_id <= 0:
        raise AdminBookingError("invalid_booking_id")
    return booking_id


def parse_admin_booking_status_command(text: str) -> tuple[int, str]:
    """Parse /booking_status ID completed|cancelled."""

    parts = text.split()
    if len(parts) != 3:
        raise AdminBookingError("invalid_booking_status_command")
    try:
        booking_id = int(parts[1])
    except ValueError as exc:
        raise AdminBookingError("invalid_booking_id") from exc
    status = parts[2].lower()
    if booking_id <= 0:
        raise AdminBookingError("invalid_booking_id")
    if status not in ADMIN_BOOKING_TARGET_STATUSES:
        raise AdminBookingError("invalid_status")
    return booking_id, status


def _safe_text(value: Any) -> str:
    """Escape DB/user-originated text for Telegram HTML parse mode."""

    return escape(str(value), quote=False)


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)


def _optional_row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        return _row_value(row, key)
    except (KeyError, AttributeError):
        return default


def _client_label(row: Any) -> str:
    username = _optional_row_value(row, "username")
    if username:
        return f"@{_safe_text(username)}"
    first_name = _optional_row_value(row, "first_name") or ""
    last_name = _optional_row_value(row, "last_name") or ""
    full_name = " ".join(part for part in (first_name, last_name) if part).strip()
    if full_name:
        return _safe_text(full_name)
    return f"tg:{_row_value(row, 'user_id')}"


def _status_marker(status: str) -> str:
    if status == "completed":
        return " ✅"
    if status == "cancelled":
        return " ❌"
    return ""


def format_admin_bookings_report(slot_date: date, rows: list[Any], *, status: str | None, language: str) -> str:
    """Format a compact admin bookings list."""

    status_label = status or "all"
    if not rows:
        return t("admin_bookings_report_empty", language, slot_date=slot_date.isoformat(), status=status_label)
    lines = [t("admin_bookings_report_title", language, slot_date=slot_date.isoformat(), status=status_label)]
    for row in rows:
        row_status = _safe_text(_row_value(row, "status"))
        lines.append(
            f"#{_row_value(row, 'booking_id')} {_safe_text(_row_value(row, 'slots_label'))} "
            f"{_client_label(row)} {row_status}{_status_marker(row_status)}"
        )
    return "\n".join(lines)


def format_admin_booking_details(row: Any, *, language: str) -> str:
    """Format detailed booking information for admins."""

    booking_id = int(_row_value(row, "booking_id"))
    status = _safe_text(_row_value(row, "status"))
    slot_date = _safe_text(_row_value(row, "slot_date"))
    pickup_time = _optional_row_value(row, "pickup_time")
    pickup_label = pickup_time.strftime("%H:%M") if hasattr(pickup_time, "strftime") else "—"
    comment = _safe_text(_optional_row_value(row, "comment") or "—")
    phone = _safe_text(_optional_row_value(row, "customer_phone") or "—")
    return "\n".join(
        [
            t("admin_booking_details_title", language, booking_id=booking_id),
            f"Статус: {status}{_status_marker(status)}",
            f"Клиент: {_client_label(row)}",
            f"Дата: {slot_date}",
            f"Слоты: {_safe_text(_row_value(row, 'slots_label'))}",
            f"Выдача: {_safe_text(pickup_label)}",
            f"Телефон: {phone}",
            f"Комментарий: {comment}",
        ]
    )


class AdminBookingsService:
    """Application service for admin booking management."""

    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def list_bookings(self, *, slot_date: date, status: str | None = None) -> list[Any]:
        if status is not None and status not in ADMIN_BOOKING_STATUSES:
            raise AdminBookingError("invalid_status")
        async with self.db_pool.acquire() as connection:
            return list(await BookingsRepository(connection).list_admin_bookings(slot_date=slot_date, status=status))

    async def get_booking_details(self, booking_id: int) -> Any:
        if booking_id <= 0:
            raise AdminBookingError("booking_not_found")
        async with self.db_pool.acquire() as connection:
            details = await BookingsRepository(connection).get_admin_booking_details(booking_id)
        if details is None:
            raise AdminBookingError("booking_not_found")
        return details

    async def set_booking_status(self, *, booking_id: int, status: str) -> dict[str, int | str | bool]:
        if booking_id <= 0:
            raise AdminBookingError("booking_not_found")
        if status not in ADMIN_BOOKING_TARGET_STATUSES:
            raise AdminBookingError("invalid_status")
        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                repository = BookingsRepository(connection)
                booking = await repository.get_by_id_for_update(booking_id)
                if booking is None:
                    raise AdminBookingError("booking_not_found")
                current_status = str(_row_value(booking, "status"))
                user_id = int(_row_value(booking, "user_id"))
                if current_status == status:
                    return {
                        "booking_id": booking_id,
                        "status": status,
                        "changed": False,
                        "review_request_pending": await repository.has_pending_review_request_job(booking_id),
                    }
                if current_status != "active":
                    raise AdminBookingError("invalid_status_transition")
                if status == "completed":
                    await repository.set_status(booking_id, "completed")
                    await repository.create_review_request_job(booking_id=booking_id, user_id=user_id)
                    return {"booking_id": booking_id, "status": status, "changed": True, "review_request_pending": True}
                if status == "cancelled":
                    await repository.set_status(booking_id, "cancelled", cancellation_reason="admin")
                    return {"booking_id": booking_id, "status": status, "changed": True, "review_request_pending": False}
        raise AdminBookingError("invalid_status_transition")
