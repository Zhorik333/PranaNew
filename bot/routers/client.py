"""Client-facing Telegram handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.keyboards.client import language_selection_keyboard, main_menu_keyboard
from bot.services.language import ensure_user_language, save_user_language

LANGUAGE_CALLBACK_PREFIX = "language:"
LANGUAGE_MENU_TEXTS = {t("menu_language", language) for language in SUPPORTED_LANGUAGES}
FREE_SLOTS_MENU_TEXTS = {t("menu_free_slots", language) for language in SUPPORTED_LANGUAGES}
REVIEWS_MENU_TEXTS = {t("menu_reviews", language) for language in SUPPORTED_LANGUAGES}


async def handle_start(message: Message, db_pool) -> None:
    """Create a user if needed and greet them in the saved language."""

    language = await ensure_user_language(db_pool, message.from_user)
    await message.answer(t("welcome", language), reply_markup=main_menu_keyboard(language))


async def handle_language_menu(message: Message, db_pool) -> None:
    """Show language choices using the user's saved language for the prompt."""

    language = await ensure_user_language(db_pool, message.from_user)
    await message.answer(t("choose_language", language), reply_markup=language_selection_keyboard())


async def handle_free_slots_menu(message: Message, db_pool) -> None:
    """Open the free-slots client screen placeholder until slot listing is implemented."""

    language = await ensure_user_language(db_pool, message.from_user)
    await message.answer(t("no_slots_available", language), reply_markup=main_menu_keyboard(language))


async def handle_reviews_menu(message: Message, db_pool) -> None:
    """Open the reviews client screen placeholder until reviews listing is implemented."""

    language = await ensure_user_language(db_pool, message.from_user)
    await message.answer(t("reviews_unavailable", language), reply_markup=main_menu_keyboard(language))


async def handle_language_selected(callback: CallbackQuery, db_pool) -> None:
    """Persist a language selected from inline callback buttons."""

    raw_language = (callback.data or "").removeprefix(LANGUAGE_CALLBACK_PREFIX)
    tg_id = callback.from_user.id if callback.from_user is not None else 0
    language = await save_user_language(db_pool, tg_id, raw_language)

    if callback.message is not None:
        await callback.message.answer(
            t("language_saved", language),
            reply_markup=main_menu_keyboard(language),
        )
    await callback.answer()


def create_client_router() -> Router:
    """Create client-facing handlers available in the MVP runtime."""

    router = Router(name="client")

    router.message.register(handle_start, CommandStart())
    router.message.register(handle_free_slots_menu, F.text.in_(FREE_SLOTS_MENU_TEXTS))
    router.message.register(handle_language_menu, F.text.in_(LANGUAGE_MENU_TEXTS))
    router.message.register(handle_reviews_menu, F.text.in_(REVIEWS_MENU_TEXTS))
    router.callback_query.register(
        handle_language_selected,
        F.data.startswith(LANGUAGE_CALLBACK_PREFIX),
    )

    return router
