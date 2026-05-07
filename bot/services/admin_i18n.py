"""Admin i18n text editing helpers."""

from __future__ import annotations

from html import escape
from typing import Any

from bot.i18n import REQUIRED_KEYS, SUPPORTED_LANGUAGES, t
from bot.repositories.i18n_texts import I18nTextsRepository


class AdminI18nError(ValueError):
    """Raised when an admin i18n command is invalid."""


def _validate_language(language: str) -> str:
    if language not in SUPPORTED_LANGUAGES:
        raise AdminI18nError("invalid_language")
    return language


def _validate_key(key: str) -> str:
    if key not in REQUIRED_KEYS:
        raise AdminI18nError("invalid_key")
    return key


def parse_set_text_command(text: str) -> tuple[str, str, str]:
    """Parse /set_text LANGUAGE KEY VALUE."""

    parts = text.split(maxsplit=3)
    if len(parts) != 4 or not parts[3].strip():
        raise AdminI18nError("invalid_set_text")
    language = _validate_language(parts[1])
    key = _validate_key(parts[2])
    value = parts[3].strip()
    return language, key, value


def parse_get_text_command(text: str) -> tuple[str, str]:
    """Parse /get_text LANGUAGE KEY."""

    parts = text.split()
    if len(parts) != 3:
        raise AdminI18nError("invalid_get_text")
    return _validate_language(parts[1]), _validate_key(parts[2])


def parse_clear_text_command(text: str) -> tuple[str, str]:
    """Parse /clear_text LANGUAGE KEY."""

    parts = text.split()
    if len(parts) != 3:
        raise AdminI18nError("invalid_clear_text")
    return _validate_language(parts[1]), _validate_key(parts[2])


def format_i18n_text_report(
    row: Any | None,
    *,
    language: str,
    key: str | None = None,
    text: str | None = None,
) -> str:
    """Format one i18n text value for an HTML admin message."""

    if row is not None:
        row_language = str(row["language"])
        row_key = str(row["key"])
        value = str(row["value"])
        source = t("admin_i18n_text_source_custom", language)
    else:
        if key is None or text is None:
            raise AdminI18nError("missing_default_text")
        row_language = language
        row_key = key
        value = text
        source = t("admin_i18n_text_source_default", language)
    return "\n".join(
        [
            t("admin_i18n_text_title", language),
            f"Language: {escape(row_language)}",
            f"Key: {escape(row_key)}",
            f"Source: {escape(source)}",
            escape(value),
        ]
    )


async def translate_with_overrides(db_pool, key: str, language: str, **kwargs: Any) -> str:
    """Translate a key, preferring a custom DB override when present."""

    language = _validate_language(language)
    key = _validate_key(key)
    if hasattr(db_pool, "acquire"):
        async with db_pool.acquire() as connection:
            row = await I18nTextsRepository(connection).get_text(language, key)
    else:
        row = await I18nTextsRepository(db_pool).get_text(language, key)
    template = str(row["value"]) if row is not None else t(key, language)
    if kwargs:
        return template.format(**kwargs)
    return template


class AdminI18nService:
    """Application service for admin-managed i18n text overrides."""

    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def set_text(self, language: str, key: str, value: str) -> None:
        language = _validate_language(language)
        key = _validate_key(key)
        value = value.strip()
        if not value:
            raise AdminI18nError("empty_text")
        async with self.db_pool.acquire() as connection:
            await I18nTextsRepository(connection).set_text(language, key, value)

    async def get_text(self, language: str, key: str):
        language = _validate_language(language)
        key = _validate_key(key)
        async with self.db_pool.acquire() as connection:
            return await I18nTextsRepository(connection).get_text(language, key)

    async def clear_text(self, language: str, key: str) -> None:
        language = _validate_language(language)
        key = _validate_key(key)
        async with self.db_pool.acquire() as connection:
            await I18nTextsRepository(connection).delete_text(language, key)
