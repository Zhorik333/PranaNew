"""Slots table repository."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from bot.repositories.base import BaseRepository


class SlotsRepository(BaseRepository):
    """Data access methods for time slots."""

    async def create_slot(
        self,
        *,
        slot_date: date,
        starts_at: time,
        start_time: datetime,
        duration_minutes: int,
        capacity: int,
    ) -> Any:
        """Create one slot and return the inserted row."""

        return await self.db.fetchrow(
            """
            INSERT INTO slots (slot_date, starts_at, start_time, duration_minutes, capacity)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, slot_date, starts_at, start_time, duration_minutes, capacity, is_blocked
            """,
            slot_date,
            starts_at,
            start_time,
            duration_minutes,
            capacity,
        )

    async def list_available(self, slot_date: date) -> list[Any]:
        """List slots with free capacity for one date.

        Occupancy is calculated from booking_slots joined to bookings where a
        booking still consumes capacity. There is no cached counter source of truth.
        """

        return await self.db.fetch(
            """
            SELECT s.id,
                   s.slot_date,
                   s.starts_at,
                   s.start_time,
                   s.duration_minutes,
                   s.capacity,
                   s.is_blocked,
                   COUNT(b.id) AS booked_count
            FROM slots s
            LEFT JOIN booking_slots bs ON bs.slot_id = s.id
            LEFT JOIN bookings b
                ON b.id = bs.booking_id
               AND b.status IN ('active', 'completed')
            WHERE s.slot_date = $1
              AND s.is_blocked = false
            GROUP BY s.id
            HAVING COUNT(b.id) < s.capacity
            ORDER BY s.starts_at ASC
            """,
            slot_date,
        )

    async def list_available_future(self, now: datetime) -> list[Any]:
        """List future slots with free capacity, ordered by start time."""

        return await self.db.fetch(
            """
            SELECT s.id,
                   s.slot_date,
                   s.starts_at,
                   s.start_time,
                   s.duration_minutes,
                   s.capacity,
                   s.is_blocked,
                   COUNT(b.id) AS booked_count
            FROM slots s
            LEFT JOIN booking_slots bs ON bs.slot_id = s.id
            LEFT JOIN bookings b
                ON b.id = bs.booking_id
               AND b.status IN ('active', 'completed')
            WHERE s.start_time > $1
              AND s.is_blocked = false
            GROUP BY s.id
            HAVING COUNT(b.id) < s.capacity
            ORDER BY s.start_time ASC
            """,
            now,
        )

    async def get_by_ids_for_update(self, slot_ids: list[int]) -> list[Any]:
        """Fetch slot rows for update, for future atomic booking transactions."""

        return await self.db.fetch(
            """
            SELECT id, slot_date, starts_at, start_time, duration_minutes, capacity, is_blocked
            FROM slots
            WHERE id = ANY($1::bigint[])
            ORDER BY start_time ASC
            FOR UPDATE
            """,
            slot_ids,
        )
