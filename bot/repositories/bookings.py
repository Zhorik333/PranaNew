"""Bookings table repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bot.repositories.base import BaseRepository


class BookingsRepository(BaseRepository):
    """Data access methods for bookings and their selected slots."""

    async def create_booking(
        self,
        *,
        user_id: int,
        slot_ids: list[int],
        customer_name: str | None,
        customer_phone: str | None,
        comment: str,
        pickup_time: datetime,
    ) -> int:
        """Create a booking row and link it to selected slots.

        Atomic transaction ownership belongs to the service layer; this method can
        run against either a pool or an acquired transaction connection.
        """

        booking_id = await self.db.fetchval(
            """
            INSERT INTO bookings (user_id, customer_name, customer_phone, comment, pickup_time)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            user_id,
            customer_name,
            customer_phone,
            comment,
            pickup_time,
        )
        for slot_id in slot_ids:
            await self.db.execute(
                """
                INSERT INTO booking_slots (booking_id, slot_id)
                VALUES ($1, $2)
                """,
                booking_id,
                slot_id,
            )
        return booking_id

    async def get_by_id(self, booking_id: int) -> Any:
        """Return one booking by id."""

        return await self.db.fetchrow(
            """
            SELECT id, user_id, status, customer_name, customer_phone, comment,
                   pickup_time, created_at, confirmed_at, completed_at, cancelled_at,
                   cancellation_reason
            FROM bookings
            WHERE id = $1
            """,
            booking_id,
        )

    async def set_status(self, booking_id: int, status: str) -> None:
        """Update booking status and relevant timestamp."""

        await self.db.execute(
            """
            UPDATE bookings
            SET status = $2,
                completed_at = CASE WHEN $2 = 'completed' THEN now() ELSE completed_at END,
                cancelled_at = CASE WHEN $2 = 'cancelled' THEN now() ELSE cancelled_at END
            WHERE id = $1
            """,
            booking_id,
            status,
        )
