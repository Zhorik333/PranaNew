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
from bot.services.admin_i18n import (
    AdminI18nError,
    AdminI18nService,
    format_i18n_text_report,
    parse_clear_text_command,
    parse_get_text_command,
    parse_set_text_command,
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
from bot.services.admin_schedule import (
    AdminScheduleError,
    AdminScheduleService,
    format_active_date_report,
    format_schedule_settings_report,
    parse_set_active_date_command,
    parse_set_schedule_command,
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


async def handle_admin_active_date_menu(message: Message, db_pool, config: Config) -> None:
    """Show active-date and schedule-settings command help from the admin menu."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        settings = await AdminScheduleService(db_pool).get_schedule_settings()
        report = format_schedule_settings_report(settings, language=ADMIN_LANGUAGE)
    except AdminScheduleError:
        report = t("admin_schedule_help", ADMIN_LANGUAGE)
    await message.answer(
        f"{t('admin_schedule_help', ADMIN_LANGUAGE)}\n\n{report}",
        reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE),
    )


async def handle_admin_set_active_date(message: Message, db_pool, config: Config) -> None:
    """Set the active booking date."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        active_date = parse_set_active_date_command(message.text or "")
        await AdminScheduleService(db_pool).set_active_date(active_date)
    except AdminScheduleError:
        await message.answer(t("admin_schedule_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(
        t("admin_active_date_updated", ADMIN_LANGUAGE, active_date=active_date.isoformat()),
        reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE),
    )


async def handle_admin_show_active_date(message: Message, db_pool, config: Config) -> None:
    """Show the current active booking date."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        active_date = await AdminScheduleService(db_pool).get_active_date()
        report = format_active_date_report(active_date, language=ADMIN_LANGUAGE)
    except AdminScheduleError:
        await message.answer(t("admin_schedule_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(report, reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_clear_active_date(message: Message, db_pool, config: Config) -> None:
    """Clear the current active booking date."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    await AdminScheduleService(db_pool).clear_active_date()
    await message.answer(t("admin_active_date_cleared", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_set_schedule(message: Message, db_pool, config: Config) -> None:
    """Set default schedule generation settings."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        start_at, end_at, step_minutes, capacity = parse_set_schedule_command(message.text or "")
        await AdminScheduleService(db_pool).set_schedule(
            start_at=start_at,
            end_at=end_at,
            step_minutes=step_minutes,
            capacity=capacity,
        )
    except AdminScheduleError:
        await message.answer(t("admin_schedule_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(t("admin_schedule_updated", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_schedule_settings(message: Message, db_pool, config: Config) -> None:
    """Show all current schedule settings."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        settings = await AdminScheduleService(db_pool).get_schedule_settings()
        report = format_schedule_settings_report(settings, language=ADMIN_LANGUAGE)
    except AdminScheduleError:
        await message.answer(t("admin_schedule_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(report, reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_i18n_menu(message: Message, db_pool, config: Config) -> None:
    """Show text editing command help from the admin menu."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    await message.answer(t("admin_i18n_help", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_set_text(message: Message, db_pool, config: Config) -> None:
    """Set a custom i18n text override."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        language, key, value = parse_set_text_command(message.text or "")
        await AdminI18nService(db_pool).set_text(language, key, value)
    except AdminI18nError:
        await message.answer(t("admin_i18n_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(t("admin_i18n_text_updated", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_get_text(message: Message, db_pool, config: Config) -> None:
    """Show a custom i18n text override or dictionary fallback."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        language, key = parse_get_text_command(message.text or "")
        row = await AdminI18nService(db_pool).get_text(language, key)
        report = format_i18n_text_report(row, language=language, key=key, text=t(key, language))
    except AdminI18nError:
        await message.answer(t("admin_i18n_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(report, reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


async def handle_admin_clear_text(message: Message, db_pool, config: Config) -> None:
    """Clear one custom i18n text override."""

    if not is_admin_chat(message, config):
        await message.answer(t("admin_only", ADMIN_LANGUAGE))
        return
    try:
        language, key = parse_clear_text_command(message.text or "")
        await AdminI18nService(db_pool).clear_text(language, key)
    except AdminI18nError:
        await message.answer(t("admin_i18n_command_error", ADMIN_LANGUAGE))
        return
    await message.answer(t("admin_i18n_text_cleared", ADMIN_LANGUAGE), reply_markup=admin_menu_keyboard(ADMIN_LANGUAGE))


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
    router.message.register(handle_admin_set_active_date, Command("set_active_date"))
    router.message.register(handle_admin_show_active_date, Command("active_date"))
    router.message.register(handle_admin_clear_active_date, Command("clear_active_date"))
    router.message.register(handle_admin_set_schedule, Command("set_schedule"))
    router.message.register(handle_admin_schedule_settings, Command("schedule_settings"))
    router.message.register(handle_admin_set_text, Command("set_text"))
    router.message.register(handle_admin_get_text, Command("get_text"))
    router.message.register(handle_admin_clear_text, Command("clear_text"))
    router.message.register(handle_admin_generate_slots_menu, F.text == t("admin_menu_generate_slots", ADMIN_LANGUAGE))
    router.message.register(handle_admin_booked_slots_menu, F.text == t("admin_menu_booked_slots", ADMIN_LANGUAGE))
    router.message.register(handle_admin_active_date_menu, F.text == t("admin_menu_active_date", ADMIN_LANGUAGE))
    router.message.register(handle_admin_i18n_menu, F.text == t("admin_menu_i18n", ADMIN_LANGUAGE))
    router.callback_query.register(
        handle_booking_complete,
        F.data.startswith(BOOKING_COMPLETE_CALLBACK_PREFIX),
    )
    return router
