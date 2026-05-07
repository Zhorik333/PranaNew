"""Repository for custom i18n text overrides."""

from __future__ import annotations

from bot.repositories.base import BaseRepository


class I18nTextsRepository(BaseRepository):
    """Data access methods for the i18n_texts override table."""

    async def set_text(self, language: str, key: str, value: str) -> None:
        """Create or update a custom text override."""

        await self.db.execute(
            """
            INSERT INTO i18n_texts (language, key, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (language, key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = now()
            """,
            language,
            key,
            value,
        )

    async def get_text(self, language: str, key: str):
        """Return one custom text override row, if present."""

        return await self.db.fetchrow(
            """
            SELECT language, key, value
            FROM i18n_texts
            WHERE language = $1
              AND key = $2
            """,
            language,
            key,
        )

    async def list_texts(self, *, language: str | None = None, limit: int = 50):
        """List custom text overrides, optionally filtered by language."""

        if language is None:
            return await self.db.fetch(
                """
                SELECT language, key, value
                FROM i18n_texts
                ORDER BY language ASC, key ASC
                LIMIT $1
                """,
                limit,
            )
        return await self.db.fetch(
            """
            SELECT language, key, value
            FROM i18n_texts
            WHERE language = $1
            ORDER BY key ASC
            LIMIT $2
            """,
            language,
            limit,
        )

    async def delete_text(self, language: str, key: str) -> None:
        """Delete one custom text override if it exists."""

        await self.db.execute(
            """
            DELETE FROM i18n_texts
            WHERE language = $1
              AND key = $2
            """,
            language,
            key,
        )
