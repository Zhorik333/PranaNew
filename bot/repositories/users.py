"""Users table repository."""

from __future__ import annotations

from typing import Any

from bot.repositories.base import BaseRepository


class UsersRepository(BaseRepository):
    """Data access methods for Telegram users."""

    async def upsert_user(
        self,
        *,
        tg_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language: str,
    ) -> None:
        """Create or update a Telegram user profile."""

        await self.db.execute(
            """
            INSERT INTO users (tg_id, username, first_name, last_name, language)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (tg_id) DO UPDATE
            SET username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                updated_at = now()
            """,
            tg_id,
            username,
            first_name,
            last_name,
            language,
        )

    async def get_by_tg_id(self, tg_id: int) -> Any:
        """Return one user by Telegram id, or None if missing."""

        return await self.db.fetchrow(
            """
            SELECT tg_id, username, first_name, last_name, language, created_at, updated_at
            FROM users
            WHERE tg_id = $1
            """,
            tg_id,
        )

    async def get_language(self, tg_id: int) -> str | None:
        """Return the saved language for a Telegram user, or None if missing."""

        return await self.db.fetchval(
            """
            SELECT language
            FROM users
            WHERE tg_id = $1
            """,
            tg_id,
        )

    async def set_language(self, tg_id: int, language: str) -> None:
        """Persist a user's selected language."""

        await self.db.execute(
            """
            UPDATE users
            SET language = $1,
                updated_at = now()
            WHERE tg_id = $2
            """,
            language,
            tg_id,
        )

    async def list_admin_users(self, *, search: str | None = None, limit: int = 20) -> list[Any]:
        """List users with booking counters for admin browsing."""

        return await self.db.fetch(
            """
            SELECT
                u.tg_id,
                u.username,
                u.first_name,
                u.last_name,
                u.language,
                u.created_at,
                u.updated_at,
                COUNT(b.id) AS bookings_count,
                COUNT(b.id) FILTER (WHERE b.status = 'active') AS active_bookings_count,
                COUNT(b.id) FILTER (WHERE b.status = 'completed') AS completed_bookings_count,
                COUNT(b.id) FILTER (WHERE b.status = 'cancelled') AS cancelled_bookings_count,
                MAX(b.created_at) AS last_booking_at
            FROM users u
            LEFT JOIN bookings b ON b.user_id = u.tg_id
            WHERE (
                $1::text IS NULL
                OR u.username ILIKE '%' || $1 || '%'
                OR u.first_name ILIKE '%' || $1 || '%'
                OR u.last_name ILIKE '%' || $1 || '%'
                OR u.tg_id::text = $1
            )
            GROUP BY u.tg_id, u.username, u.first_name, u.last_name,
                     u.language, u.created_at, u.updated_at
            ORDER BY MAX(b.created_at) DESC NULLS LAST, u.created_at DESC, u.tg_id ASC
            LIMIT $2
            """,
            search,
            limit,
        )

    async def get_admin_user_details(self, tg_id: int) -> Any:
        """Return one user with booking counters for admin inspection."""

        return await self.db.fetchrow(
            """
            SELECT
                u.tg_id,
                u.username,
                u.first_name,
                u.last_name,
                u.language,
                u.created_at,
                u.updated_at,
                COUNT(b.id) AS bookings_count,
                COUNT(b.id) FILTER (WHERE b.status = 'active') AS active_bookings_count,
                COUNT(b.id) FILTER (WHERE b.status = 'completed') AS completed_bookings_count,
                COUNT(b.id) FILTER (WHERE b.status = 'cancelled') AS cancelled_bookings_count,
                MAX(b.created_at) AS last_booking_at
            FROM users u
            LEFT JOIN bookings b ON b.user_id = u.tg_id
            WHERE u.tg_id = $1
            GROUP BY u.tg_id, u.username, u.first_name, u.last_name,
                     u.language, u.created_at, u.updated_at
            """,
            tg_id,
        )

    async def list_admin_user_booking_history(self, *, user_id: int, limit: int = 10) -> list[Any]:
        """List one user's booking history with aggregated slot labels."""

        return await self.db.fetch(
            """
            SELECT
                b.id AS booking_id,
                b.status,
                b.pickup_time,
                b.created_at,
                b.comment,
                MIN(s.slot_date) AS slot_date,
                string_agg(to_char(s.starts_at, 'HH24:MI'), ', ' ORDER BY s.starts_at) AS slots_label
            FROM bookings b
            JOIN booking_slots bs ON bs.booking_id = b.id
            JOIN slots s ON s.id = bs.slot_id
            WHERE b.user_id = $1
            GROUP BY b.id, b.status, b.pickup_time, b.created_at, b.comment
            ORDER BY b.created_at DESC, b.id DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
