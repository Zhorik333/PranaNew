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

    async def get_admin_notification_details(self, booking_id: int) -> Any:
        """Return booking details needed for compact admin notifications."""

        return await self.db.fetchrow(
            """
            SELECT
                b.id AS booking_id,
                b.user_id,
                u.username,
                u.first_name,
                u.last_name,
                MIN(s.slot_date) AS slot_date,
                string_agg(to_char(s.starts_at, 'HH24:MI'), ', ' ORDER BY s.starts_at) AS slots_label,
                b.pickup_time
            FROM bookings b
            JOIN users u ON u.tg_id = b.user_id
            JOIN booking_slots bs ON bs.booking_id = b.id
            JOIN slots s ON s.id = bs.slot_id
            WHERE b.id = $1
            GROUP BY b.id, b.user_id, u.username, u.first_name, u.last_name, b.pickup_time
            """,
            booking_id,
        )

    async def list_admin_bookings(self, *, slot_date, status: str | None = None) -> list[Any]:
        """List bookings for an admin date report, optionally filtered by status."""

        return await self.db.fetch(
            """
            SELECT
                b.id AS booking_id,
                b.user_id,
                b.status,
                b.customer_name,
                b.customer_phone,
                b.comment,
                b.pickup_time,
                b.created_at,
                u.username,
                u.first_name,
                u.last_name,
                MIN(s.slot_date) AS slot_date,
                string_agg(to_char(s.starts_at, 'HH24:MI'), ', ' ORDER BY s.starts_at) AS slots_label
            FROM bookings b
            JOIN users u ON u.tg_id = b.user_id
            JOIN booking_slots bs ON bs.booking_id = b.id
            JOIN slots s ON s.id = bs.slot_id
            WHERE s.slot_date = $1
              AND ($2::text IS NULL OR b.status = $2)
            GROUP BY b.id, b.user_id, b.status, b.customer_name, b.customer_phone,
                     b.comment, b.pickup_time, b.created_at,
                     u.username, u.first_name, u.last_name
            ORDER BY MIN(s.starts_at) ASC, b.id ASC
            """,
            slot_date,
            status,
        )

    async def get_admin_booking_details(self, booking_id: int) -> Any:
        """Return detailed booking information for admin inspection."""

        return await self.db.fetchrow(
            """
            SELECT
                b.id AS booking_id,
                b.user_id,
                b.status,
                b.customer_name,
                b.customer_phone,
                b.comment,
                b.pickup_time,
                b.created_at,
                b.confirmed_at,
                b.completed_at,
                b.cancelled_at,
                u.username,
                u.first_name,
                u.last_name,
                MIN(s.slot_date) AS slot_date,
                string_agg(to_char(s.starts_at, 'HH24:MI'), ', ' ORDER BY s.starts_at) AS slots_label
            FROM bookings b
            JOIN users u ON u.tg_id = b.user_id
            JOIN booking_slots bs ON bs.booking_id = b.id
            JOIN slots s ON s.id = bs.slot_id
            WHERE b.id = $1
            GROUP BY b.id, b.user_id, b.status, b.customer_name, b.customer_phone,
                     b.comment, b.pickup_time, b.created_at, b.confirmed_at,
                     b.completed_at, b.cancelled_at,
                     u.username, u.first_name, u.last_name
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

    async def create_review_request_job(self, *, booking_id: int, user_id: int) -> None:
        """Persist a pending review request notification for a completed booking."""

        await self.db.execute(
            """
            INSERT INTO scheduler_jobs (job_type, payload, run_at, status)
            VALUES (
                'review_request',
                jsonb_build_object('booking_id', $1::bigint, 'user_id', $2::bigint),
                now(),
                'pending'
            )
            """,
            booking_id,
            user_id,
        )

    async def has_pending_review_request_job(self, booking_id: int) -> bool:
        """Return True when a review request still needs to be sent."""

        pending_job_id = await self.db.fetchval(
            """
            SELECT id
            FROM scheduler_jobs
            WHERE job_type = 'review_request'
              AND status = 'pending'
              AND (payload->>'booking_id')::bigint = $1
            ORDER BY id
            LIMIT 1
            """,
            booking_id,
        )
        return pending_job_id is not None

    async def claim_due_review_request_job(self) -> Any:
        """Atomically claim the oldest due review request job for background delivery."""

        return await self.db.fetchrow(
            """
            UPDATE scheduler_jobs
            SET status = 'running', attempts = attempts + 1, updated_at = now()
            WHERE id = (
                SELECT id
                FROM scheduler_jobs
                WHERE job_type = 'review_request'
                  AND (
                    (status = 'pending' AND run_at <= now())
                    OR (status = 'running' AND updated_at <= now() - interval '5 minutes')
                  )
                ORDER BY run_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, payload
            """,
        )

    async def mark_scheduler_job_done(self, job_id: int) -> None:
        """Mark a claimed scheduler job as delivered."""

        await self.db.execute(
            """
            UPDATE scheduler_jobs
            SET status = 'done', updated_at = now()
            WHERE id = $1
              AND status = 'running'
            """,
            job_id,
        )

    async def restore_scheduler_job_pending(self, job_id: int, last_error: str) -> None:
        """Restore a claimed scheduler job to pending after delivery failure."""

        await self.db.execute(
            """
            UPDATE scheduler_jobs
            SET status = 'pending',
                run_at = now() + interval '5 minutes',
                last_error = $2,
                updated_at = now()
            WHERE id = $1
              AND status = 'running'
            """,
            job_id,
            last_error,
        )

    async def claim_pending_review_request_job(self, booking_id: int) -> bool:
        """Atomically claim the oldest pending review request job for delivery."""

        claimed_job_id = await self.db.fetchval(
            """
            UPDATE scheduler_jobs
            SET status = 'running', attempts = attempts + 1, updated_at = now()
            WHERE id = (
                SELECT id
                FROM scheduler_jobs
                WHERE job_type = 'review_request'
                  AND status = 'pending'
                  AND (payload->>'booking_id')::bigint = $1
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id
            """,
            booking_id,
        )
        return claimed_job_id is not None

    async def mark_review_request_job_done(self, booking_id: int) -> None:
        """Mark the running review request for a booking as delivered."""

        await self.db.execute(
            """
            UPDATE scheduler_jobs
            SET status = 'done', updated_at = now()
            WHERE id = (
                SELECT id
                FROM scheduler_jobs
                WHERE job_type = 'review_request'
                  AND status = 'running'
                  AND (payload->>'booking_id')::bigint = $1
                ORDER BY id
                LIMIT 1
            )
            """,
            booking_id,
        )

    async def restore_review_request_job_pending(self, booking_id: int, last_error: str) -> None:
        """Restore a claimed review request job so a later callback can retry it."""

        await self.db.execute(
            """
            UPDATE scheduler_jobs
            SET status = 'pending', last_error = $2, updated_at = now()
            WHERE id = (
                SELECT id
                FROM scheduler_jobs
                WHERE job_type = 'review_request'
                  AND status = 'running'
                  AND (payload->>'booking_id')::bigint = $1
                ORDER BY id
                LIMIT 1
            )
            """,
            booking_id,
            last_error,
        )
