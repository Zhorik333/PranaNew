"""Analytics event and report repository."""

from __future__ import annotations

from datetime import date
from typing import Any

from bot.repositories.base import BaseRepository


class AnalyticsRepository(BaseRepository):
    """Data access for lightweight analytics metrics."""

    async def record_event(self, *, event_type: str, user_id: int | None = None, booking_id: int | None = None) -> None:
        """Persist one analytics event."""

        await self.db.execute(
            """
            INSERT INTO analytics_events (event_type, user_id, booking_id)
            VALUES ($1, $2, $3)
            """,
            event_type,
            user_id,
            booking_id,
        )

    async def record_free_slots_view(self, *, user_id: int | None = None) -> None:
        """Persist one free-slot screen view event."""

        await self.record_event(event_type="free_slots_view", user_id=user_id)

    async def get_daily_report(self, *, slot_date: date) -> Any:
        """Return basic booking and slot-load metrics for one slot date."""

        return await self.db.fetchrow(
            """
            WITH booking_metrics AS (
                SELECT
                    COUNT(DISTINCT b.id) AS created_bookings,
                    COUNT(DISTINCT b.id) FILTER (WHERE b.status = 'active') AS active_bookings,
                    COUNT(DISTINCT b.id) FILTER (WHERE b.status = 'cancelled') AS cancelled_bookings,
                    COUNT(DISTINCT b.id) FILTER (WHERE b.status = 'completed') AS completed_bookings
                FROM bookings b
                JOIN booking_slots bs ON bs.booking_id = b.id
                JOIN slots s ON s.id = bs.slot_id
                WHERE s.slot_date = $1
            ),
            slot_metrics AS (
                SELECT
                    COUNT(*) AS total_slots,
                    COALESCE(SUM(capacity), 0) AS total_capacity
                FROM slots
                WHERE slot_date = $1
            ),
            occupancy_metrics AS (
                SELECT COUNT(bs.booking_id) FILTER (WHERE b.status IN ('active', 'completed')) AS occupied_slots
                FROM slots s
                LEFT JOIN booking_slots bs ON bs.slot_id = s.id
                LEFT JOIN bookings b ON b.id = bs.booking_id
                WHERE s.slot_date = $1
            ),
            view_metrics AS (
                SELECT COUNT(*) FILTER (WHERE event_type = 'free_slots_view') AS free_slots_views
                FROM analytics_events
                WHERE created_at::date = $1
            )
            SELECT
                $1::date AS slot_date,
                COALESCE(v.free_slots_views, 0)::bigint AS free_slots_views,
                COALESCE(bm.created_bookings, 0)::bigint AS created_bookings,
                COALESCE(bm.active_bookings, 0)::bigint AS active_bookings,
                COALESCE(bm.cancelled_bookings, 0)::bigint AS cancelled_bookings,
                COALESCE(bm.completed_bookings, 0)::bigint AS completed_bookings,
                COALESCE(sm.total_slots, 0)::bigint AS total_slots,
                COALESCE(sm.total_capacity, 0)::bigint AS total_capacity,
                COALESCE(om.occupied_slots, 0)::bigint AS occupied_slots
            FROM booking_metrics bm
            CROSS JOIN slot_metrics sm
            CROSS JOIN occupancy_metrics om
            CROSS JOIN view_metrics v
            """,
            slot_date,
        )
