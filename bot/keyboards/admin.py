"""Admin-facing Telegram keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.i18n import t
from bot.services.bookings import build_booking_complete_callback_data, build_review_request_callback_data


ADMIN_MENU_LANGUAGE = "ru"


def admin_menu_keyboard(language: str = ADMIN_MENU_LANGUAGE) -> ReplyKeyboardMarkup:
    """Build the persistent admin menu keyboard."""

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin_menu_generate_slots", language)),
                KeyboardButton(text=t("admin_menu_booked_slots", language)),
            ],
            [
                KeyboardButton(text=t("admin_menu_active_date", language)),
                KeyboardButton(text=t("admin_menu_reviews", language)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def booking_complete_keyboard(booking_id: int, *, language: str) -> InlineKeyboardMarkup:
    """Build a one-button inline keyboard to mark a booking completed."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("complete_booking", language),
                    callback_data=build_booking_complete_callback_data(booking_id),
                )
            ]
        ]
    )


def review_request_keyboard(booking_id: int, *, language: str) -> InlineKeyboardMarkup:
    """Build an inline keyboard for the future review flow."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("leave_review", language),
                    callback_data=build_review_request_callback_data(booking_id),
                )
            ]
        ]
    )
