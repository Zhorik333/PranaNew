"""Client-facing Telegram keyboards."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.i18n import t
from bot.services.slots import SLOT_CALLBACK_PREFIX, format_slot_label

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


def available_slots_keyboard(slots: list[Any], *, columns: int = 3) -> InlineKeyboardMarkup:
    """Build inline buttons for available slots."""

    buttons = [
        InlineKeyboardButton(
            text=format_slot_label(slot),
            callback_data=f"{SLOT_CALLBACK_PREFIX}{slot['id'] if isinstance(slot, dict) else slot['id']}",
        )
        for slot in slots
    ]
    rows = [buttons[index : index + columns] for index in range(0, len(buttons), columns)]
    return InlineKeyboardMarkup(inline_keyboard=rows)
