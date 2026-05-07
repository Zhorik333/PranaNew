"""Client-facing Telegram keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.i18n import t

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
