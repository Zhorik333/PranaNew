"""Client-facing Telegram handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.keyboards.client import (
    available_slots_keyboard,
    booking_preview_keyboard,
    language_selection_keyboard,
    main_menu_keyboard,
)
from bot.services.language import ensure_user_language, get_user_language, save_user_language
from bot.services.slots import (
    BOOKING_PREVIEW_CALLBACK_PREFIX,
    BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX,
    DEFAULT_MAX_CONSECUTIVE_SLOTS,
    SLOT_CALLBACK_PREFIX,
    SlotSelectionError,
    format_booking_preview_text,
    list_available_slots,
    parse_booking_preview_callback_data,
    parse_slot_callback_data,
    toggle_slot_selection,
)

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
    """Show available future slots as inline buttons."""

    language = await ensure_user_language(db_pool, message.from_user)
    slots = await list_available_slots(db_pool)
    if not slots:
        await message.answer(t("no_slots_available", language), reply_markup=main_menu_keyboard(language))
        return
    await message.answer(t("choose_slot", language), reply_markup=available_slots_keyboard(slots))


async def handle_reviews_menu(message: Message, db_pool) -> None:
    """Open the reviews client screen placeholder until reviews listing is implemented."""

    language = await ensure_user_language(db_pool, message.from_user)
    await message.answer(t("reviews_unavailable", language), reply_markup=main_menu_keyboard(language))


async def handle_slot_selected(callback: CallbackQuery, db_pool) -> None:
    """Toggle one slot selection and redraw inline slot buttons."""

    tg_id = callback.from_user.id if callback.from_user is not None else 0
    language = await get_user_language(db_pool, tg_id)
    try:
        clicked_slot_id, selected_slot_ids = parse_slot_callback_data(callback.data or "")
        slots = await list_available_slots(db_pool)
        new_selected_ids = toggle_slot_selection(
            slots,
            selected_slot_ids=selected_slot_ids,
            clicked_slot_id=clicked_slot_id,
        )
    except SlotSelectionError as error:
        error_key = str(error)
        if error_key == "max_consecutive":
            await callback.answer(
                t("max_consecutive_error", language, max_slots=DEFAULT_MAX_CONSECUTIVE_SLOTS),
                show_alert=True,
            )
        elif error_key == "non_consecutive":
            await callback.answer(t("non_consecutive_error", language), show_alert=True)
        else:
            await callback.answer(t("slot_unavailable_error", language), show_alert=True)
        return
    except ValueError:
        await callback.answer(t("slot_unavailable_error", language), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=available_slots_keyboard(slots, selected_slot_ids=new_selected_ids, language=language))
    await callback.answer(t("slot_selected" if clicked_slot_id in new_selected_ids else "slot_unselected", language), show_alert=False)


async def handle_booking_preview(callback: CallbackQuery, db_pool) -> None:
    """Show a preview of the selected slots before booking confirmation."""

    tg_id = callback.from_user.id if callback.from_user is not None else 0
    language = await get_user_language(db_pool, tg_id)
    try:
        selected_slot_ids = parse_booking_preview_callback_data(callback.data or "")
        slots = await list_available_slots(db_pool)
        preview_text = format_booking_preview_text(slots, selected_slot_ids, language)
    except SlotSelectionError as error:
        error_key = str(error)
        if error_key in {"preview_empty_selection", "empty_selection"}:
            await callback.answer(t("preview_empty_selection_error", language), show_alert=True)
        elif error_key == "max_consecutive":
            await callback.answer(
                t("max_consecutive_error", language, max_slots=DEFAULT_MAX_CONSECUTIVE_SLOTS),
                show_alert=True,
            )
        elif error_key == "non_consecutive":
            await callback.answer(t("non_consecutive_error", language), show_alert=True)
        else:
            await callback.answer(t("slot_unavailable_error", language), show_alert=True)
        return
    except ValueError:
        await callback.answer(t("preview_empty_selection_error", language), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(
            preview_text,
            reply_markup=booking_preview_keyboard(selected_slot_ids, language=language),
        )
    await callback.answer()


async def handle_booking_preview_change(callback: CallbackQuery, db_pool) -> None:
    """Return from booking preview to the slot selection screen with current selection."""

    tg_id = callback.from_user.id if callback.from_user is not None else 0
    language = await get_user_language(db_pool, tg_id)
    try:
        selected_slot_ids = parse_booking_preview_callback_data(
            callback.data or "",
            prefix=BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX,
        )
    except ValueError:
        await callback.answer(t("preview_empty_selection_error", language), show_alert=True)
        return

    slots = await list_available_slots(db_pool)
    if callback.message is not None:
        await callback.message.edit_text(
            t("choose_slot", language),
            reply_markup=available_slots_keyboard(slots, selected_slot_ids=selected_slot_ids, language=language),
        )
    await callback.answer()


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
        handle_booking_preview,
        F.data.startswith(BOOKING_PREVIEW_CALLBACK_PREFIX),
    )
    router.callback_query.register(
        handle_booking_preview_change,
        F.data.startswith(BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX),
    )
    router.callback_query.register(
        handle_slot_selected,
        F.data.startswith(SLOT_CALLBACK_PREFIX),
    )
    router.callback_query.register(
        handle_language_selected,
        F.data.startswith(LANGUAGE_CALLBACK_PREFIX),
    )

    return router
