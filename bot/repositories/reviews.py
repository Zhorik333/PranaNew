"""Reviews table repository."""

from __future__ import annotations

from typing import Any

from bot.repositories.base import BaseRepository


class ReviewsRepository(BaseRepository):
    """Data access methods for client reviews."""

    async def get_completed_booking_for_review(self, *, booking_id: int, user_id: int) -> Any | None:
        """Lock and return a completed booking owned by the user for review."""

        return await self.db.fetchrow(
            """
            SELECT id, user_id, status
            FROM bookings
            WHERE id = $1
              AND user_id = $2
              AND status = 'completed'
            FOR UPDATE
            """,
            booking_id,
            user_id,
        )

    async def get_by_booking_id(self, booking_id: int) -> Any | None:
        """Return an existing review for a booking if present."""

        return await self.db.fetchrow(
            """
            SELECT id, booking_id, user_id, status, text, rating, created_at, moderated_at
            FROM reviews
            WHERE booking_id = $1
            """,
            booking_id,
        )

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

    async def list_published(self, *, limit: int = 10, offset: int = 0) -> list[Any]:
        """Return the newest published reviews with user labels."""

        return await self.db.fetch(
            """
            SELECT r.id, r.booking_id, r.user_id, r.status, r.text, r.rating, r.created_at, r.moderated_at,
                   u.username, NULLIF(concat_ws(' ', u.first_name, u.last_name), '') AS full_name
            FROM reviews r
            LEFT JOIN users u ON u.tg_id = r.user_id
            WHERE r.status = 'published'
            ORDER BY r.created_at DESC
            LIMIT $1
            OFFSET $2
            """,
            limit,
            offset,
        )

    async def list_for_moderation(self, *, status: str = "pending", limit: int = 10) -> list[Any]:
        """Return reviews for admin moderation with user labels."""

        if status == "all":
            return await self.db.fetch(
                """
                SELECT r.id, r.booking_id, r.user_id, r.status, r.text, r.rating, r.created_at, r.moderated_at,
                       u.username, NULLIF(concat_ws(' ', u.first_name, u.last_name), '') AS full_name
                FROM reviews r
                LEFT JOIN users u ON u.tg_id = r.user_id
                ORDER BY r.created_at DESC
                LIMIT $1
                """,
                limit,
            )
        return await self.db.fetch(
            """
            SELECT r.id, r.booking_id, r.user_id, r.status, r.text, r.rating, r.created_at, r.moderated_at,
                   u.username, NULLIF(concat_ws(' ', u.first_name, u.last_name), '') AS full_name
            FROM reviews r
            LEFT JOIN users u ON u.tg_id = r.user_id
            WHERE r.status = $1
            ORDER BY r.created_at DESC
            LIMIT $2
            """,
            status,
            limit,
        )

    async def review_details(self, review_id: int) -> Any | None:
        """Return one review with user labels for admin display."""

        return await self.db.fetchrow(
            """
            SELECT r.id, r.booking_id, r.user_id, r.status, r.text, r.rating, r.created_at, r.moderated_at,
                   u.username, NULLIF(concat_ws(' ', u.first_name, u.last_name), '') AS full_name
            FROM reviews r
            LEFT JOIN users u ON u.tg_id = r.user_id
            WHERE r.id = $1
            """,
            review_id,
        )

    async def lock_review_for_moderation(self, review_id: int, *, expected_status: str = "pending") -> Any | None:
        """Lock a review before changing moderation status."""

        return await self.db.fetchrow(
            """
            SELECT id, booking_id, user_id, status, text, rating, created_at, moderated_at
            FROM reviews
            WHERE id = $1
              AND status = $2
            FOR UPDATE
            """,
            review_id,
            expected_status,
        )

    async def set_status(self, review_id: int, status: str) -> Any | None:
        """Moderate a review and return the updated row."""

        return await self.db.fetchrow(
            """
            UPDATE reviews
            SET status = $2,
                moderated_at = now()
            WHERE id = $1
            RETURNING id, booking_id, user_id, status, text, rating, created_at, moderated_at
            """,
            review_id,
            status,
        )
