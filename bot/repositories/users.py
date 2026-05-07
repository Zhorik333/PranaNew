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
                language = EXCLUDED.language,
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
