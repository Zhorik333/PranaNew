"""Admin-facing Telegram keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import t
from bot.services.bookings import build_booking_complete_callback_data, build_review_request_callback_data


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
