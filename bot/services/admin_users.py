"""Admin user listing and booking history helpers."""

from __future__ import annotations

from html import escape
from typing import Any

from bot.i18n import t
from bot.repositories.users import UsersRepository

DEFAULT_USERS_LIMIT = 20
DEFAULT_HISTORY_LIMIT = 10
MAX_USERS_LIMIT = 100
MAX_HISTORY_LIMIT = 50


class AdminUserError(ValueError):
    """Raised when an admin user command is invalid or not found."""


def parse_admin_users_command(text: str) -> tuple[str | None, int]:
    """Parse /users [search] [limit]."""

    parts = text.split()
    if len(parts) > 3:
        raise AdminUserError("invalid_users_command")
    search = None
    limit = DEFAULT_USERS_LIMIT
    if len(parts) >= 2:
        search = parts[1].strip() or None
    if len(parts) == 3:
        limit = _parse_limit(parts[2], max_limit=MAX_USERS_LIMIT)
    return search, limit


def parse_admin_user_command(text: str) -> int:
    """Parse /user TG_ID."""

    parts = text.split()
    if len(parts) != 2:
        raise AdminUserError("invalid_user_id")
    return _parse_user_id(parts[1])


def parse_admin_user_history_command(text: str) -> tuple[int, int]:
    """Parse /user_history TG_ID [limit]."""

    parts = text.split()
    if len(parts) not in {2, 3}:
        raise AdminUserError("invalid_user_history_command")
    user_id = _parse_user_id(parts[1])
    limit = DEFAULT_HISTORY_LIMIT
    if len(parts) == 3:
        limit = _parse_limit(parts[2], max_limit=MAX_HISTORY_LIMIT)
    return user_id, limit


def _parse_user_id(value: str) -> int:
    try:
        user_id = int(value)
    except ValueError as exc:
        raise AdminUserError("invalid_user_id") from exc
    if user_id <= 0:
        raise AdminUserError("invalid_user_id")
    return user_id


def _parse_limit(value: str, *, max_limit: int) -> int:
    try:
        limit = int(value)
    except ValueError as exc:
        raise AdminUserError("invalid_limit") from exc
    if limit <= 0 or limit > max_limit:
        raise AdminUserError("invalid_limit")
    return limit


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


def _safe_text(value: Any) -> str:
    return escape(str(value), quote=False)


def _client_label(row: Any) -> str:
    username = _optional_row_value(row, "username")
    if username:
        return f"@{_safe_text(username)}"
    first_name = _optional_row_value(row, "first_name") or ""
    last_name = _optional_row_value(row, "last_name") or ""
    full_name = " ".join(part for part in (first_name, last_name) if part).strip()
    if full_name:
        return _safe_text(full_name)
    return f"tg:{_row_value(row, 'tg_id')}"


def _status_marker(status: str) -> str:
    if status == "completed":
        return " ✅"
    if status == "cancelled":
        return " ❌"
    return ""


def format_admin_users_report(rows: list[Any], *, search: str | None, language: str) -> str:
    """Format a compact admin users report."""

    if not rows:
        return t("admin_users_report_empty", language)
    lines = [t("admin_users_report_title", language)]
    for row in rows:
        tg_id = int(_row_value(row, "tg_id"))
        bookings_count = int(_optional_row_value(row, "bookings_count", 0) or 0)
        active_count = int(_optional_row_value(row, "active_bookings_count", 0) or 0)
        completed_count = int(_optional_row_value(row, "completed_bookings_count", 0) or 0)
        cancelled_count = int(_optional_row_value(row, "cancelled_bookings_count", 0) or 0)
        lines.append(
            f"tg:{tg_id} {_client_label(row)} "
            f"броней:{bookings_count} active:{active_count} completed:{completed_count} cancelled:{cancelled_count}"
        )
    return "\n".join(lines)


def format_admin_user_details(row: Any, *, language: str) -> str:
    """Format one user's admin details."""

    tg_id = int(_row_value(row, "tg_id"))
    bookings_count = int(_optional_row_value(row, "bookings_count", 0) or 0)
    active_count = int(_optional_row_value(row, "active_bookings_count", 0) or 0)
    completed_count = int(_optional_row_value(row, "completed_bookings_count", 0) or 0)
    cancelled_count = int(_optional_row_value(row, "cancelled_bookings_count", 0) or 0)
    language_code = _safe_text(_optional_row_value(row, "language", "—") or "—")
    created_at = _safe_text(_optional_row_value(row, "created_at", "—") or "—")
    updated_at = _safe_text(_optional_row_value(row, "updated_at", "—") or "—")
    last_booking_at = _safe_text(_optional_row_value(row, "last_booking_at", "—") or "—")
    return "\n".join(
        [
            t("admin_user_details_title", language, user_id=tg_id),
            f"Клиент: {_client_label(row)}",
            f"Язык: {language_code}",
            f"Брони: {bookings_count}",
            f"Активные: {active_count}",
            f"Выданные: {completed_count}",
            f"Отменённые: {cancelled_count}",
            f"Последняя бронь: {last_booking_at}",
            f"Создан: {created_at}",
            f"Обновлён: {updated_at}",
        ]
    )


def format_admin_user_history(user_id: int, rows: list[Any], *, language: str) -> str:
    """Format a user's booking history."""

    if not rows:
        return t("admin_user_history_empty", language, user_id=user_id)
    lines = [t("admin_user_history_title", language, user_id=user_id)]
    for row in rows:
        status = _safe_text(_row_value(row, "status"))
        slot_date = _safe_text(_row_value(row, "slot_date"))
        slots_label = _safe_text(_row_value(row, "slots_label"))
        lines.append(f"#{_row_value(row, 'booking_id')} {slot_date} {slots_label} {status}{_status_marker(status)}")
    return "\n".join(lines)


class AdminUsersService:
    """Application service for admin user browsing and history."""

    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def list_users(self, *, search: str | None = None, limit: int = DEFAULT_USERS_LIMIT) -> list[Any]:
        if limit <= 0 or limit > MAX_USERS_LIMIT:
            raise AdminUserError("invalid_limit")
        async with self.db_pool.acquire() as connection:
            return list(await UsersRepository(connection).list_admin_users(search=search, limit=limit))

    async def get_user_details(self, user_id: int) -> Any:
        if user_id <= 0:
            raise AdminUserError("invalid_user_id")
        async with self.db_pool.acquire() as connection:
            details = await UsersRepository(connection).get_admin_user_details(user_id)
        if details is None:
            raise AdminUserError("user_not_found")
        return details

    async def list_user_history(self, *, user_id: int, limit: int = DEFAULT_HISTORY_LIMIT) -> list[Any]:
        if user_id <= 0:
            raise AdminUserError("invalid_user_id")
        if limit <= 0 or limit > MAX_HISTORY_LIMIT:
            raise AdminUserError("invalid_limit")
        async with self.db_pool.acquire() as connection:
            return list(await UsersRepository(connection).list_admin_user_booking_history(user_id=user_id, limit=limit))
