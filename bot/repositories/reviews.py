"""Reviews table repository."""

from __future__ import annotations

from typing import Any

from bot.repositories.base import BaseRepository


class ReviewsRepository(BaseRepository):
    """Data access methods for client reviews."""

    async def create_review(
        self,
        *,
        booking_id: int,
        user_id: int,
        text: str,
        rating: int | None = None,
    ) -> Any:
        """Create a pending review and return it."""

        return await self.db.fetchrow(
            """
            INSERT INTO reviews (booking_id, user_id, text, rating)
            VALUES ($1, $2, $3, $4)
            RETURNING id, booking_id, user_id, status, text, rating, created_at, moderated_at
            """,
            booking_id,
            user_id,
            text,
            rating,
        )

    async def list_published(self, *, limit: int = 10) -> list[Any]:
        """Return the newest published reviews."""

        return await self.db.fetch(
            """
            SELECT id, booking_id, user_id, status, text, rating, created_at, moderated_at
            FROM reviews
            WHERE status = 'published'
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )

    async def set_status(self, review_id: int, status: str) -> None:
        """Moderate a review."""

        await self.db.execute(
            """
            UPDATE reviews
            SET status = $2,
                moderated_at = now()
            WHERE id = $1
            """,
            review_id,
            status,
        )
