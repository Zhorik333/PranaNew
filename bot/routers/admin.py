"""Admin-facing Telegram handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.i18n import t
from bot.keyboards.admin import admin_menu_keyboard, review_request_keyboard
from bot.services.admin_bookings import (
    AdminBookingError,
    AdminBookingsService,
    format_admin_booking_details,
    format_admin_bookings_report,
    parse_admin_booking_detail_command,
    parse_admin_booking_status_command,
    parse_admin_bookings_command,
)
from bot.services.admin_users import (
    AdminUserError,
    AdminUsersService,
    format_admin_user_details,
    format_admin_user_history,
    format_admin_users_report,
    parse_admin_user_command,
    parse_admin_user_history_command,
    parse_admin_users_command,
)
from bot.services.admin_slots import (
    AdminSlotError,
    AdminSlotsService,
    parse_block_slot_command,
    parse_capacity_command,
    parse_generate_slots_command,
    parse_list_slots_command,
)
from bot.services.bookings import (
    BOOKING_COMPLETE_CALLBACK_PREFIX,
    BookingCompletionError,
    BookingService,
    parse_booking_complete_callback_data,
)

ADMIN_LANGUAGE = "ru"


def is_admin_chat(message: Message, config: Config) -> bool:
    """Return true when a message belongs to the configured admin chat."""

    return message.chat.id == config.admin_chat_id


async def handle_chat_id(message: Message) -> None:
    """Show the current Telegram chat id for setup."""

    await message.answer(t("admin_chat_id", ADMIN_LANGUAGE, chat_id=message.chat.id))


async def handle_admin_entry(message: Message, config: Config) -> None:
    """Open the admin menu only inside the configured admin chat."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return

    await message.answer(t("admin_menu_title", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_generate_slots_menu(message: Message, config: Config) -> None:
    """Show slot generation command help from the admin menu."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    await message.answer(t("admin_generate_slots_help", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_booked_slots_menu(message: Message, config: Config) -> None:
    """Show slot and booking list command help from the admin menu."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    help_text = "\n".join(
        [
            t("admin_booked_slots_help", ADMIN_LANGUAGE),
            t("admin_bookings_help", ADMIN_LANGUAGE),
            t("admin_users_help", ADMIN_LANGUAGE),
        ]
    )
    await message.answer(help_text, reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_users_list(message: Message, db_pool, config: Config) -> None:
    """List users with booking counters."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        search, limit = parse_admin_users_command(message.text or "")
        rows = await AdminUsersService(db_pool).list_users(search=search, limit=limit)
        report = format_admin_users_report(rows, search=search, language=ADMIN_LANGUAGE)
    except AdminUserError:
        await message.answer(t("admin_user_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(report, reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_user_detail(message: Message, db_pool, config: Config) -> None:
    """Show one user's profile and booking counters."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        user_id = parse_admin_user_command(message.text or "")
        details = await AdminUsersService(db_pool).get_user_details(user_id)
    except AdminUserError:
        await message.answer(t("admin_user_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(format_admin_user_details(details, language=ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_user_history(message: Message, db_pool, config: Config) -> None:
    """Show one user's booking history."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        user_id, limit = parse_admin_user_history_command(message.text or "")
        rows = await AdminUsersService(db_pool).list_user_history(user_id=user_id, limit=limit)
        report = format_admin_user_history(user_id, rows, language=ADMIN_LANGUAGE)
    except AdminUserError:
        await message.answer(t("admin_user_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(report, reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_booking_list(message: Message, db_pool, config: Config) -> None:
    """List bookings by date and optional status."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        slot_date, status = parse_admin_bookings_command(message.text or "")
        rows = await AdminBookingsService(db_pool).list_bookings(slot_date=slot_date, status=status)
        report = format_admin_bookings_report(slot_date, rows, status=status, language=ADMIN_LANGUAGE)
    except AdminBookingError:
        await message.answer(t("admin_booking_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(report, reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_booking_detail(message: Message, db_pool, config: Config) -> None:
    """Show one booking details by id."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        booking_id = parse_admin_booking_detail_command(message.text or "")
        details = await AdminBookingsService(db_pool).get_booking_details(booking_id)
    except AdminBookingError:
        await message.answer(t("admin_booking_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(format_admin_booking_details(details, language=ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_booking_status(message: Message, db_pool, config: Config) -> None:
    """Change one booking status from an admin command."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        booking_id, status = parse_admin_booking_status_command(message.text or "")
        result = await AdminBookingsService(db_pool).set_booking_status(booking_id=booking_id, status=status)
    except AdminBookingError:
        await message.answer(t("admin_booking_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(
        t("admin_booking_status_updated", ADMIN_LANGUAGE, booking_id=result["booking_id"], status=result["status"]),
        reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE),
    )


async def handle_admin_slot_generate(message: Message, db_pool, config: Config) -> None:
    """Generate slots from an admin command."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        slot_date, step, start_at, end_at, capacity = parse_generate_slots_command(message.text or "")
        count = await AdminSlotsService(db_pool).generate_slots(
            slot_date=slot_date,
            step_minutes=step,
            start_at=start_at,
            end_at=end_at,
            capacity=capacity,
            tz_name=config.default_tz,
        )
    except AdminSlotError:
        await message.answer(t("admin_slot_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(t("admin_slots_generated", ADMIN_LANGUAGE, count=count), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_slot_list(message: Message, db_pool, config: Config) -> None:
    """List all slots for one date with occupancy and blocked state."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        slot_date = parse_list_slots_command(message.text or "")
        report = await AdminSlotsService(db_pool).list_slots_report(slot_date, language=ADMIN_LANGUAGE)
    except AdminSlotError:
        await message.answer(t("admin_slot_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(report, reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_slot_block(message: Message, db_pool, config: Config) -> None:
    """Block one slot by id."""

    await _handle_admin_slot_block_state(message, db_pool, config, is_blocked=True)


async def handle_admin_slot_unblock(message: Message, db_pool, config: Config) -> None:
    """Unblock one slot by id."""

    await _handle_admin_slot_block_state(message, db_pool, config, is_blocked=False)


async def _handle_admin_slot_block_state(message: Message, db_pool, config: Config, *, is_blocked: bool) -> None:
    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        slot_id = parse_block_slot_command(message.text or "")
        await AdminSlotsService(db_pool).set_blocked(slot_id=slot_id, is_blocked=is_blocked)
    except AdminSlotError:
        await message.answer(t("admin_slot_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(t("admin_slot_updated", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_slot_capacity(message: Message, db_pool, config: Config) -> None:
    """Change one slot capacity."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        slot_id, capacity = parse_capacity_command(message.text or "")
        await AdminSlotsService(db_pool).set_capacity(slot_id=slot_id, capacity=capacity)
    except AdminSlotError:
        await message.answer(t("admin_slot_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(t("admin_slot_updated", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


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
    router.message.register(handle_chat_id, Command("chatid"))
    router.message.register(handle_admin_entry, Command("admin"))
    router.message.register(handle_admin_slot_generate, Command("generate"))
    router.message.register(handle_admin_slot_list, Command("admin_slots"))
    router.message.register(handle_admin_slot_block, Command("block_slot"))
    router.message.register(handle_admin_slot_unblock, Command("unblock_slot"))
    router.message.register(handle_admin_slot_capacity, Command("set_capacity"))
    router.message.register(handle_admin_booking_list, Command("bookings"))
    router.message.register(handle_admin_booking_detail, Command("booking"))
    router.message.register(handle_admin_booking_status, Command("booking_status"))
    router.message.register(handle_admin_users_list, Command("users"))
    router.message.register(handle_admin_user_detail, Command("user"))
    router.message.register(handle_admin_user_history, Command("user_history"))
    router.message.register(handle_admin_generate_slots_menu, F.text == t("admin_menu_generate_slots", ADMIN_LANGUAGE))
    router.message.register(handle_admin_booked_slots_menu, F.text == t("admin_menu_booked_slots", ADMIN_LANGUAGE))
    router.callback_query.register(
        handle_booking_complete,
        F.data.startswith(BOOKING_COMPLETE_CALLBACK_PREFIX),
    )
    return router
