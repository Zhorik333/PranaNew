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
        status: str = "active",
    ) -> int:
        """Create a booking row and link it to selected slots.

        Atomic transaction ownership belongs to the service layer; this method can
        run against either a pool or an acquired transaction connection.
        """

        booking_id = await self.db.fetchval(
            """
            INSERT INTO bookings (user_id, status, customer_name, customer_phone, comment, pickup_time)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            user_id,
            status,
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

    async def find_active_by_user_and_slot_ids(self, *, user_id: int, slot_ids: list[int]) -> int | None:
        """Return an active booking for this user with exactly the selected slots."""

        return await self.db.fetchval(
            """
            WITH matching_booking AS (
                SELECT b.id, ARRAY_AGG(bs.slot_id ORDER BY bs.slot_id) AS booked_slot_ids
                FROM bookings b
                JOIN booking_slots bs ON bs.booking_id = b.id
                WHERE b.user_id = $1
                  AND b.status = 'active'
                GROUP BY b.id
            )
            SELECT id
            FROM matching_booking
            WHERE booked_slot_ids = (
                SELECT ARRAY_AGG(slot_id ORDER BY slot_id)
                FROM UNNEST($2::bigint[]) AS selected(slot_id)
            )
            LIMIT 1
            """,
            user_id,
            slot_ids,
        )

    async def count_consuming_bookings_by_slot_ids(self, slot_ids: list[int]) -> list[Any]:
        """Count active/completed bookings that consume capacity for each slot."""

        return await self.db.fetch(
            """
            SELECT bs.slot_id, COUNT(b.id) AS booked_count
            FROM booking_slots bs
            JOIN bookings b ON b.id = bs.booking_id
            WHERE bs.slot_id = ANY($1::bigint[])
              AND b.status IN ('active', 'completed')
            GROUP BY bs.slot_id
            """,
            slot_ids,
        )

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

    async def get_by_id_for_update(self, booking_id: int) -> Any:
        """Lock and return one booking by id for status transitions."""

        return await self.db.fetchrow(
            """
            SELECT id, user_id, status, customer_name, customer_phone, comment,
                   pickup_time, created_at, confirmed_at, completed_at, cancelled_at,
                   cancellation_reason
            FROM bookings
            WHERE id = $1
            FOR UPDATE
            """,
            booking_id,
        )

    async def set_status(self, booking_id: int, status: str, *, cancellation_reason: str | None = None) -> None:
        """Update booking status and relevant timestamp."""

        await self.db.execute(
            """
            UPDATE bookings
            SET status = $2,
                completed_at = CASE WHEN $2 = 'completed' THEN now() ELSE completed_at END,
                cancelled_at = CASE WHEN $2 = 'cancelled' THEN now() ELSE cancelled_at END,
                cancellation_reason = CASE WHEN $2 = 'cancelled' THEN $3 ELSE cancellation_reason END
            WHERE id = $1
            """,
            booking_id,
            status,
            cancellation_reason,
        )
