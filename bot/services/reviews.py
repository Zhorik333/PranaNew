"""Client review collection service."""

from __future__ import annotations

from typing import Any

from bot.repositories.reviews import ReviewsRepository
from bot.services.bookings import REVIEW_REQUEST_CALLBACK_PREFIX

MAX_REVIEW_TEXT_LENGTH = 1000


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


def _value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)


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
