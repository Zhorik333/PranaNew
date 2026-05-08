"""Client-facing Telegram handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.keyboards.admin import booking_complete_keyboard
from bot.keyboards.client import (
    available_slots_keyboard,
    booking_preview_keyboard,
    booking_cancel_keyboard,
    language_selection_keyboard,
    main_menu_keyboard,
    public_reviews_keyboard,
)
from bot.services.booking_notifications import (
    format_admin_booking_cancelled_message,
    format_admin_new_booking_message,
)
from bot.services.admin_i18n import translate_with_overrides
from bot.services.bookings import BookingCancellationError, BookingCreationError, BookingService, REVIEW_REQUEST_CALLBACK_PREFIX
from bot.services.language import ensure_user_language, get_user_language, save_user_language
from bot.services.reviews import (
    PUBLIC_REVIEWS_MORE_CALLBACK_PREFIX,
    PublicReviewsService,
    ReviewCollectionError,
    ReviewService,
    format_public_reviews_report,
    parse_public_reviews_more_callback_data,
    parse_review_request_callback_data,
)
from bot.services.slots import (
    BOOKING_PREVIEW_CALLBACK_PREFIX,
    BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX,
    BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX,
    BOOKING_CANCEL_CALLBACK_PREFIX,
    DEFAULT_MAX_CONSECUTIVE_SLOTS,
    SLOT_CALLBACK_PREFIX,
    SlotSelectionError,
    format_booking_preview_text,
    list_available_slots,
    parse_booking_cancel_callback_data,
    parse_booking_preview_callback_data,
    parse_slot_callback_data,
    toggle_slot_selection,
)

from bot.states.reviews import ReviewStates

LANGUAGE_CALLBACK_PREFIX = "language:"
LANGUAGE_MENU_TEXTS = {t("menu_language", language) for language in SUPPORTED_LANGUAGES}
FREE_SLOTS_MENU_TEXTS = {t("menu_free_slots", language) for language in SUPPORTED_LANGUAGES}
REVIEWS_MENU_TEXTS = {t("menu_reviews", language) for language in SUPPORTED_LANGUAGES}


async def handle_start(message: Message, db_pool) -> None:
    """Create a user if needed and greet them in the saved language."""

    language = await ensure_user_language(db_pool, message.from_user)
    welcome_text = await translate_with_overrides(db_pool, "welcome", language)
    await message.answer(welcome_text, reply_markup=main_menu_keyboard(language))


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
    """Show the first page of published reviews to clients."""

    language = await ensure_user_language(db_pool, message.from_user)
    page = await PublicReviewsService(db_pool).list_published_page(page=1)
    reply_markup = public_reviews_keyboard(next_page=page.next_page, language=language) or main_menu_keyboard(language)
    await message.answer(format_public_reviews_report(page.reviews, language=language), reply_markup=reply_markup)


async def handle_public_reviews_more(callback: CallbackQuery, db_pool) -> None:
    """Show the next page of published reviews from an inline pagination button."""

    tg_id = callback.from_user.id if callback.from_user is not None else 0
    language = await get_user_language(db_pool, tg_id)
    try:
        page_number = parse_public_reviews_more_callback_data(callback.data or "")
    except ValueError:
        await callback.answer(t("published_reviews_empty", language), show_alert=True)
        return

    page = await PublicReviewsService(db_pool).list_published_page(page=page_number)
    if not page.reviews:
        await callback.answer(t("published_reviews_empty", language), show_alert=True)
        return
    if callback.message is not None:
        await callback.message.edit_text(
            format_public_reviews_report(page.reviews, language=language),
            reply_markup=public_reviews_keyboard(next_page=page.next_page, language=language),
        )
    await callback.answer()


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


async def handle_booking_confirm(callback: CallbackQuery, db_pool, config=None) -> None:
    """Atomically confirm a booking from selected slot ids."""

    tg_id = callback.from_user.id if callback.from_user is not None else 0
    language = await get_user_language(db_pool, tg_id)
    booking_service = BookingService(db_pool)
    try:
        selected_slot_ids = parse_booking_preview_callback_data(
            callback.data or "",
            prefix=BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX,
        )
        booking_id = await booking_service.create_booking(user_id=tg_id, selected_slot_ids=selected_slot_ids)
    except (ValueError, BookingCreationError) as error:
        error_key = str(error)
        if error_key == "max_consecutive":
            await callback.answer(
                t("max_consecutive_error", language, max_slots=DEFAULT_MAX_CONSECUTIVE_SLOTS),
                show_alert=True,
            )
        elif error_key == "non_consecutive":
            await callback.answer(t("non_consecutive_error", language), show_alert=True)
        else:
            await callback.answer(t("booking_unavailable", language), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(
            t("booking_confirmed", language, booking_id=booking_id),
            reply_markup=booking_cancel_keyboard(booking_id, language=language),
        )
    bot = getattr(callback, "bot", None)
    if config is not None and bot is not None:
        try:
            details = await booking_service.get_admin_notification_details(booking_id=booking_id)
            if details is not None:
                await bot.send_message(
                    config.admin_chat_id,
                    format_admin_new_booking_message(details, language="ru"),
                    reply_markup=booking_complete_keyboard(booking_id, language="ru"),
                )
        except Exception:
            pass
    await callback.answer()


async def handle_booking_cancel(callback: CallbackQuery, db_pool, config=None) -> None:
    """Cancel an active booking owned by the current user."""

    tg_id = callback.from_user.id if callback.from_user is not None else 0
    language = await get_user_language(db_pool, tg_id)
    booking_service = BookingService(db_pool)
    try:
        booking_id = parse_booking_cancel_callback_data(callback.data or "")
        details = None
        if config is not None and getattr(callback, "bot", None) is not None:
            try:
                details = await booking_service.get_admin_notification_details(booking_id=booking_id)
            except Exception:
                details = None
        changed = await booking_service.cancel_booking(user_id=tg_id, booking_id=booking_id)
    except (ValueError, BookingCancellationError):
        await callback.answer(t("booking_cancel_unavailable", language), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(t("booking_cancelled", language, booking_id=booking_id))
    bot = getattr(callback, "bot", None)
    if changed and details is not None and config is not None and bot is not None:
        try:
            await bot.send_message(
                config.admin_chat_id,
                format_admin_booking_cancelled_message(details, language="ru"),
            )
        except Exception:
            pass
    await callback.answer()


async def handle_review_request(callback: CallbackQuery, db_pool, state: FSMContext) -> None:
    """Start one-step review collection after a completed booking."""

    tg_id = callback.from_user.id if callback.from_user is not None else 0
    language = await get_user_language(db_pool, tg_id)
    try:
        booking_id = parse_review_request_callback_data(callback.data or "")
        await ReviewService(db_pool).can_review(booking_id=booking_id, user_id=tg_id)
    except (ValueError, ReviewCollectionError) as error:
        await state.clear()
        if str(error) == "review_already_exists":
            await callback.answer(t("review_already_exists", language), show_alert=True)
        else:
            await callback.answer(t("review_unavailable", language), show_alert=True)
        return

    await state.update_data(booking_id=booking_id)
    await state.set_state(ReviewStates.waiting_for_text)
    if callback.message is not None:
        await callback.message.answer(t("review_prompt", language), reply_markup=main_menu_keyboard(language))
    await callback.answer()


async def handle_review_text(message: Message, db_pool, state: FSMContext) -> None:
    """Persist review text from the FSM state."""

    tg_id = message.from_user.id if message.from_user is not None else 0
    language = await get_user_language(db_pool, tg_id)
    data = await state.get_data()
    try:
        booking_id = int(data.get("booking_id", 0))
        await ReviewService(db_pool).submit_review(
            booking_id=booking_id,
            user_id=tg_id,
            text=message.text or "",
        )
    except ReviewCollectionError as error:
        if str(error) == "empty_review":
            await message.answer(t("review_empty_error", language), reply_markup=main_menu_keyboard(language))
        elif str(error) == "review_already_exists":
            await state.clear()
            await message.answer(t("review_already_exists", language), reply_markup=main_menu_keyboard(language))
        else:
            await state.clear()
            await message.answer(t("review_unavailable", language), reply_markup=main_menu_keyboard(language))
        return
    except (TypeError, ValueError):
        await state.clear()
        await message.answer(t("review_unavailable", language), reply_markup=main_menu_keyboard(language))
        return

    await state.clear()
    await message.answer(t("review_saved", language), reply_markup=main_menu_keyboard(language))


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
    router.message.register(handle_review_text, ReviewStates.waiting_for_text)
    router.callback_query.register(
        handle_public_reviews_more,
        F.data.startswith(PUBLIC_REVIEWS_MORE_CALLBACK_PREFIX),
    )
    router.callback_query.register(
        handle_booking_cancel,
        F.data.startswith(BOOKING_CANCEL_CALLBACK_PREFIX),
    )
    router.callback_query.register(
        handle_booking_confirm,
        F.data.startswith(BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX),
    )
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
        handle_review_request,
        F.data.startswith(REVIEW_REQUEST_CALLBACK_PREFIX),
    )
    router.callback_query.register(
        handle_language_selected,
        F.data.startswith(LANGUAGE_CALLBACK_PREFIX),
    )

    return router
