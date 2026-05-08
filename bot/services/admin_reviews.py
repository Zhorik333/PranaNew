"""Admin review moderation helpers."""

from __future__ import annotations

from html import escape
from typing import Any

from bot.i18n import t
from bot.repositories.reviews import ReviewsRepository

REVIEW_STATUSES = {"pending", "published", "rejected", "all"}
MODERATION_TARGET_STATUSES = {"published", "rejected"}
MAX_ADMIN_REVIEWS_LIMIT = 50
MIN_REVIEW_RATING = 1
MAX_REVIEW_RATING = 5


class AdminReviewError(ValueError):
    """Raised for invalid admin review commands or transitions."""


def parse_admin_reviews_command(text: str) -> tuple[str, int]:
    """Parse `/reviews [pending|published|rejected|all] [limit]`."""

    parts = (text or "").split()
    if not parts or parts[0] != "/reviews" or len(parts) > 3:
        raise AdminReviewError("invalid_reviews_command")
    status = "pending"
    limit = 10
    if len(parts) >= 2:
        status = parts[1].lower()
    if status not in REVIEW_STATUSES:
        raise AdminReviewError("invalid_review_status")
    if len(parts) == 3:
        try:
            limit = int(parts[2])
        except ValueError as exc:
            raise AdminReviewError("invalid_limit") from exc
    if limit < 1:
        raise AdminReviewError("invalid_limit")
    return status, min(limit, MAX_ADMIN_REVIEWS_LIMIT)


def parse_admin_review_command(text: str) -> int:
    """Parse `/review REVIEW_ID`."""

    parts = (text or "").split()
    if len(parts) != 2 or parts[0] != "/review":
        raise AdminReviewError("invalid_review_command")
    try:
        review_id = int(parts[1])
    except ValueError as exc:
        raise AdminReviewError("invalid_review_id") from exc
    if review_id <= 0:
        raise AdminReviewError("invalid_review_id")
    return review_id


def parse_admin_review_status_command(text: str) -> tuple[int, str]:
    """Parse `/review_status REVIEW_ID published|rejected`."""

    parts = (text or "").split()
    if len(parts) != 3 or parts[0] != "/review_status":
        raise AdminReviewError("invalid_review_status_command")
    try:
        review_id = int(parts[1])
    except ValueError as exc:
        raise AdminReviewError("invalid_review_id") from exc
    status = parts[2].lower()
    if review_id <= 0 or status not in MODERATION_TARGET_STATUSES:
        raise AdminReviewError("invalid_review_status")
    return review_id, status


def _value(row: Any, key: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key, default)


def _client_label(row: Any) -> str:
    username = _value(row, "username", None)
    full_name = _value(row, "full_name", None)
    user_id = _value(row, "user_id", "")
    if username:
        return f"@{escape(str(username))}"
    if full_name:
        return escape(str(full_name))
    return str(user_id)


def _format_rating_stars(rating: Any) -> str:
    try:
        value = int(rating)
    except (TypeError, ValueError):
        return "—"
    if not MIN_REVIEW_RATING <= value <= MAX_REVIEW_RATING:
        return "—"
    return "★" * value + "☆" * (MAX_REVIEW_RATING - value)


def _format_review_row(row: Any) -> str:
    review_id = _value(row, "id")
    booking_id = _value(row, "booking_id")
    status = escape(str(_value(row, "status")))
    text = escape(str(_value(row, "text", "")))
    if len(text) > 160:
        text = f"{text[:157]}..."
    rating = _format_rating_stars(_value(row, "rating", None))
    return f"#{review_id} booking #{booking_id} [{status}] {rating} {_client_label(row)} — {text}"


def format_admin_reviews_report(rows: list[Any], *, status: str, language: str = "ru") -> str:
    """Format a compact admin review list."""

    if not rows:
        return t("admin_reviews_report_empty", language, status=status)
    lines = [t("admin_reviews_report_title", language, status=status)]
    lines.extend(_format_review_row(row) for row in rows)
    return "\n".join(lines)


def format_admin_review_details(row: Any, *, language: str = "ru") -> str:
    """Format one review with full text for moderation."""

    review_id = _value(row, "id")
    return "\n".join(
        [
            t("admin_review_details_title", language, review_id=review_id),
            f"Booking: #{_value(row, 'booking_id')}",
            f"Client: {_client_label(row)} ({_value(row, 'user_id')})",
            f"Status: {escape(str(_value(row, 'status')))}",
            f"Rating: {_format_rating_stars(_value(row, 'rating', None))}",
            f"Text: {escape(str(_value(row, 'text', '')))}",
            "",
            f"/review_status {review_id} published",
            f"/review_status {review_id} rejected",
        ]
    )


class AdminReviewsService:
    """Admin service for review moderation."""

    def __init__(self, db_pool: Any) -> None:
        self.db_pool = db_pool

    async def list_reviews(self, *, status: str = "pending", limit: int = 10) -> list[Any]:
        if status not in REVIEW_STATUSES or limit < 1:
            raise AdminReviewError("invalid_review_list")
        return await ReviewsRepository(self.db_pool).list_for_moderation(status=status, limit=min(limit, MAX_ADMIN_REVIEWS_LIMIT))

    async def get_review_details(self, review_id: int) -> Any:
        if review_id <= 0:
            raise AdminReviewError("invalid_review_id")
        row = await ReviewsRepository(self.db_pool).review_details(review_id)
        if row is None:
            raise AdminReviewError("review_not_found")
        return row

    async def set_review_status(self, *, review_id: int, status: str) -> Any:
        if review_id <= 0 or status not in MODERATION_TARGET_STATUSES:
            raise AdminReviewError("invalid_review_status")
        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                repository = ReviewsRepository(connection)
                locked = await repository.lock_review_for_moderation(review_id, expected_status="pending")
                if locked is None:
                    raise AdminReviewError("review_transition_not_allowed")
                updated = await repository.set_status(review_id, status)
                if updated is None:
                    raise AdminReviewError("review_not_found")
                return updated
