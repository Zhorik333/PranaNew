"""Admin-facing Telegram handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.config import Config
from bot.i18n import t
from bot.keyboards.admin import review_request_keyboard
from bot.services.bookings import (
    BOOKING_COMPLETE_CALLBACK_PREFIX,
    BookingCompletionError,
    BookingService,
    parse_booking_complete_callback_data,
)

ADMIN_LANGUAGE = "ru"


async def handle_booking_complete(callback: CallbackQuery, db_pool, config: Config) -> None:
    """Mark a booking as completed from the admin chat and request a review."""

    chat_id = callback.message.chat.id if callback.message is not None else None
    if chat_id != config.admin_chat_id:
        await callback.answer(t("admin_only", ADMIN_LANGUAGE), show_alert=True)
        return

    try:
        booking_id = parse_booking_complete_callback_data(callback.data or "")
        booking_service = BookingService(db_pool)
        result = await booking_service.complete_booking(booking_id=booking_id)
    except (ValueError, BookingCompletionError):
        await callback.answer(t("booking_complete_unavailable", ADMIN_LANGUAGE), show_alert=True)
        return

    bot = getattr(callback, "bot", None)
    if result["review_request_pending"] and bot is not None:
        claimed = await booking_service.claim_review_request(booking_id=booking_id)
        if claimed:
            try:
                await bot.send_message(
                    int(result["user_id"]),
                    t("review_request", ADMIN_LANGUAGE),
                    reply_markup=review_request_keyboard(booking_id, language=ADMIN_LANGUAGE),
                )
            except Exception:
                await booking_service.restore_review_request_retry(booking_id=booking_id)
                await callback.answer(t("booking_complete_unavailable", ADMIN_LANGUAGE), show_alert=True)
                return
            await booking_service.mark_review_request_sent(booking_id=booking_id)

    if not result["changed"]:
        await callback.answer(t("booking_completed", ADMIN_LANGUAGE, booking_id=booking_id), show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(t("booking_completed", ADMIN_LANGUAGE, booking_id=booking_id))

    await callback.answer()


def create_admin_router() -> Router:
    """Create admin handlers for booking management callbacks."""

    router = Router(name="admin")
    router.callback_query.register(
        handle_booking_complete,
        F.data.startswith(BOOKING_COMPLETE_CALLBACK_PREFIX),
    )
    return router
