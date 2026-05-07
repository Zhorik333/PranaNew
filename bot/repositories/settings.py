"""Settings table repository."""

from __future__ import annotations

from bot.repositories.base import BaseRepository


class SettingsRepository(BaseRepository):
    """Data access methods for key-value bot settings."""

    async def set(self, key: str, value: str) -> None:
        """Create or update one setting."""

        await self.db.execute(
            """
            INSERT INTO settings (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = now()
            """,
            key,
            value,
        )

    async def get(self, key: str, default: str | None = None) -> str | None:
        """Return a setting value, falling back to default when missing."""

        value = await self.db.fetchval(
            """
            SELECT value
            FROM settings
            WHERE key = $1
            """,
            key,
        )
        return default if value is None else value

    async def delete(self, key: str) -> None:
        """Delete one setting if it exists."""

        await self.db.execute(
            """
            DELETE FROM settings
            WHERE key = $1
            """,
            key,
        )
