"""Language selection helpers for Telegram users."""

from __future__ import annotations

from typing import Protocol

from bot.i18n import DEFAULT_LANGUAGE, normalize_language
from bot.repositories import UsersRepository


class TelegramUser(Protocol):
    """Minimal Telegram user shape needed by the language service."""

    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None


async def ensure_user_language(db_pool, telegram_user: TelegramUser | None) -> str:
    """Ensure a Telegram user exists and return the persisted language."""

    if telegram_user is None:
        return DEFAULT_LANGUAGE

    repository = UsersRepository(db_pool)
    existing = await repository.get_by_tg_id(telegram_user.id)
    if existing is not None:
        return normalize_language(existing.get("language") if hasattr(existing, "get") else existing["language"])

    language = normalize_language(telegram_user.language_code)
    await repository.upsert_user(
        tg_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
        language=language,
    )
    return language


async def get_user_language(db_pool, tg_id: int, *, default: str = DEFAULT_LANGUAGE) -> str:
    """Return the saved user language or a normalized default."""

    repository = UsersRepository(db_pool)
    language = await repository.get_language(tg_id)
    return normalize_language(language or default)


async def save_user_language(db_pool, tg_id: int, language: str) -> str:
    """Persist a supported language and return the normalized value."""

    normalized_language = normalize_language(language)
    repository = UsersRepository(db_pool)
    await repository.set_language(tg_id, normalized_language)
    return normalized_language
