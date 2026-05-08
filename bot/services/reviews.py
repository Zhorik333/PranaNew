"""Client review collection service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from typing import Any

from bot.i18n import t
from bot.repositories.reviews import ReviewsRepository
from bot.services.bookings import REVIEW_REQUEST_CALLBACK_PREFIX

MAX_REVIEW_TEXT_LENGTH = 1000
MAX_PUBLIC_REVIEWS_LIMIT = 20
MAX_PUBLIC_REVIEW_TEXT_LENGTH = 500
MAX_PUBLIC_REVIEW_AUTHOR_LENGTH = 80
MAX_PUBLIC_REVIEWS_MESSAGE_LENGTH = 3900
PUBLIC_REVIEWS_PAGE_SIZE = 10
PUBLIC_REVIEWS_MORE_CALLBACK_PREFIX = "reviews_more:"


@dataclass(frozen=True)
class PublicReviewsPage:
    """One page of public reviews plus pagination metadata."""

    reviews: list[Any]
    page: int
    page_size: int
    has_next: bool

    @property
    def next_page(self) -> int | None:
        if not self.has_next:
            return None
        return self.page + 1


class ReviewCollectionError(ValueError):
    """Raised when a user cannot submit a review."""


def parse_review_request_callback_data(callback_data: str) -> int:
    """Parse leave-review callback data into a booking id."""

    if not callback_data.startswith(REVIEW_REQUEST_CALLBACK_PREFIX):
        raise ValueError("Invalid review callback data")
    booking_id = int(callback_data.removeprefix(REVIEW_REQUEST_CALLBACK_PREFIX))
    if booking_id <= 0:
        raise ValueError("Booking id must be positive")
    return booking_id


def build_public_reviews_more_callback_data(page: int) -> str:
    """Build callback data for loading a public reviews page."""

    page_number = int(page)
    if page_number <= 0:
        raise ValueError("Page must be positive")
    return f"{PUBLIC_REVIEWS_MORE_CALLBACK_PREFIX}{page_number}"


def parse_public_reviews_more_callback_data(callback_data: str) -> int:
    """Parse public reviews pagination callback data into a page number."""

    if not callback_data.startswith(PUBLIC_REVIEWS_MORE_CALLBACK_PREFIX):
        raise ValueError("Invalid public reviews callback data")
    raw_page = callback_data.removeprefix(PUBLIC_REVIEWS_MORE_CALLBACK_PREFIX)
    if not raw_page.isascii() or not raw_page.isdecimal() or raw_page.startswith("0"):
        raise ValueError("Invalid public reviews callback data")
    page = int(raw_page)
    if page <= 0:
        raise ValueError("Page must be positive")
    return page


def _value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)


def _format_review_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value or "")


def _public_author_label(row: Any) -> str:
    username = _value_or_none(row, "username")
    full_name = _value_or_none(row, "full_name")
    if username:
        return "@" + str(username)
    if full_name:
        return str(full_name)
    return "—"


def _value_or_none(row: Any, key: str) -> Any | None:
    try:
        return _value(row, key)
    except (KeyError, AttributeError, TypeError):
        return None


def _truncate_public_review_text(text: str, *, max_length: int = MAX_PUBLIC_REVIEW_TEXT_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def _truncate_public_author_label(author: str, *, max_length: int = MAX_PUBLIC_REVIEW_AUTHOR_LENGTH) -> str:
    if len(author) <= max_length:
        return author
    return author[: max_length - 1].rstrip() + "…"


def format_public_reviews_report(rows: list[Any], *, language: str = "ru") -> str:
    """Format published reviews for client display using HTML-safe text and Telegram-safe length."""

    if not rows:
        return t("published_reviews_empty", language)

    lines = [t("published_reviews_title", language)]
    current_text = "\n".join(lines)
    for row in rows:
        author = escape(_truncate_public_author_label(_public_author_label(row)))
        raw_text = str(_value_or_none(row, "text") or "")
        text = escape(_truncate_public_review_text(raw_text))
        created_at = _format_review_date(_value_or_none(row, "created_at"))
        review_lines = ["", f"• <b>{author}</b> · {escape(created_at)}", text]
        candidate = current_text + "\n" + "\n".join(review_lines)
        if len(candidate) > MAX_PUBLIC_REVIEWS_MESSAGE_LENGTH:
            break
        lines.extend(review_lines)
        current_text = candidate
    return current_text


class PublicReviewsService:
    """Read published reviews for public client display."""

    def __init__(self, db_pool: Any) -> None:
        self.db_pool = db_pool

    async def list_published_reviews(self, *, limit: int = 10) -> list[Any]:
        safe_limit = min(max(1, int(limit)), MAX_PUBLIC_REVIEWS_LIMIT)
        return await ReviewsRepository(self.db_pool).list_published(limit=safe_limit)

    async def list_published_page(
        self,
        *,
        page: int = 1,
        page_size: int = PUBLIC_REVIEWS_PAGE_SIZE,
    ) -> PublicReviewsPage:
        page_number = max(1, int(page))
        safe_page_size = min(max(1, int(page_size)), MAX_PUBLIC_REVIEWS_LIMIT)
        offset = (page_number - 1) * safe_page_size
        rows = await ReviewsRepository(self.db_pool).list_published(limit=safe_page_size + 1, offset=offset)
        return PublicReviewsPage(
            reviews=list(rows[:safe_page_size]),
            page=page_number,
            page_size=safe_page_size,
            has_next=len(rows) > safe_page_size,
        )


class ReviewService:
    """Validate and persist one review per completed booking."""

    def __init__(self, db_pool: Any) -> None:
        self.db_pool = db_pool

    async def can_review(self, *, booking_id: int, user_id: int) -> None:
        """Validate that a user may review a completed booking."""

        await self._validate_booking_for_review(booking_id=booking_id, user_id=user_id)

    async def submit_review(self, *, booking_id: int, user_id: int, text: str, rating: int | None = None) -> Any:
        """Create a pending review for a completed booking owned by the user."""

        cleaned_text = (text or "").strip()
        if not cleaned_text:
            raise ReviewCollectionError("empty_review")
        if len(cleaned_text) > MAX_REVIEW_TEXT_LENGTH:
            cleaned_text = cleaned_text[:MAX_REVIEW_TEXT_LENGTH]
        if rating is not None and not 1 <= int(rating) <= 5:
            raise ReviewCollectionError("invalid_rating")

        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                repository = ReviewsRepository(connection)
                await self._validate_booking_for_review(
                    booking_id=booking_id,
                    user_id=user_id,
                    repository=repository,
                )
                return await repository.create_review(
                    booking_id=booking_id,
                    user_id=user_id,
                    text=cleaned_text,
                    rating=rating,
                )

    async def _validate_booking_for_review(
        self,
        *,
        booking_id: int,
        user_id: int,
        repository: ReviewsRepository | None = None,
    ) -> None:
        if booking_id <= 0:
            raise ReviewCollectionError("review_unavailable")
        if repository is not None:
            booking = await repository.get_completed_booking_for_review(booking_id=booking_id, user_id=user_id)
            existing_review = await repository.get_by_booking_id(booking_id)
        else:
            async with self.db_pool.acquire() as connection:
                async with connection.transaction():
                    local_repository = ReviewsRepository(connection)
                    booking = await local_repository.get_completed_booking_for_review(booking_id=booking_id, user_id=user_id)
                    existing_review = await local_repository.get_by_booking_id(booking_id)
        if booking is None or str(_value(booking, "status")) != "completed":
            raise ReviewCollectionError("review_unavailable")
        if existing_review is not None:
            raise ReviewCollectionError("review_already_exists")
