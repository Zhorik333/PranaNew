"""Client-facing Telegram keyboards."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.i18n import t
from bot.services.slots import (
    build_booking_preview_callback_data,
    build_booking_preview_change_callback_data,
    build_booking_preview_confirm_callback_data,
    build_slot_callback_data,
    format_slot_label,
    slot_id,
)

LANGUAGE_LABELS = {
    "ru": "Русский",
    "en": "English",
    "sr": "Srpski",
}


def main_menu_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Build the persistent client main menu for the selected language."""

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("menu_free_slots", language))],
            [
                KeyboardButton(text=t("menu_language", language)),
                KeyboardButton(text=t("menu_reviews", language)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def language_selection_keyboard() -> InlineKeyboardMarkup:
    """Build inline language choice buttons."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=LANGUAGE_LABELS["ru"], callback_data="language:ru")],
            [InlineKeyboardButton(text=LANGUAGE_LABELS["en"], callback_data="language:en")],
            [InlineKeyboardButton(text=LANGUAGE_LABELS["sr"], callback_data="language:sr")],
        ]
    )


def available_slots_keyboard(
    slots: list[Any],
    *,
    columns: int = 3,
    selected_slot_ids: list[int] | None = None,
    language: str = "ru",
) -> InlineKeyboardMarkup:
    """Build inline buttons for available slots."""

    selected_ids = selected_slot_ids or []
    selected_id_set = set(selected_ids)
    buttons = [
        InlineKeyboardButton(
            text=f"✅ {format_slot_label(slot)}" if slot_id(slot) in selected_id_set else format_slot_label(slot),
            callback_data=build_slot_callback_data(slot_id(slot), selected_ids),
        )
        for slot in slots
    ]
    rows = [buttons[index : index + columns] for index in range(0, len(buttons), columns)]
    if selected_ids:
        rows.append([InlineKeyboardButton(text=t("done", language), callback_data=build_booking_preview_callback_data(selected_ids))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_preview_keyboard(selected_slot_ids: list[int], *, language: str) -> InlineKeyboardMarkup:
    """Build confirm/change buttons for the booking preview screen."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("confirm", language),
                    callback_data=build_booking_preview_confirm_callback_data(selected_slot_ids),
                ),
                InlineKeyboardButton(
                    text=t("change", language),
                    callback_data=build_booking_preview_change_callback_data(selected_slot_ids),
                ),
            ]
        ]
    )
