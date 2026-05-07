"""Dictionary-based i18n messages for PranaNew."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_LANGUAGE = "ru"
SUPPORTED_LANGUAGES = {"ru", "en", "sr"}

REQUIRED_KEYS = (
    "welcome",
    "menu_free_slots",
    "menu_language",
    "menu_reviews",
    "choose_language",
    "language_saved",
    "no_slots_available",
    "slot_selected",
    "slot_unselected",
    "non_consecutive_error",
    "max_consecutive_error",
    "slot_unavailable_error",
    "preview_title",
    "pickup_time",
    "confirm",
    "change",
    "booking_confirmed",
    "review_request",
    "review_saved",
    "reviews_unavailable",
)

MESSAGES: Mapping[str, Mapping[str, str]] = {
    "ru": {
        "welcome": "Добро пожаловать в PranaNew. Выберите действие в меню.",
        "menu_free_slots": "Свободные слоты",
        "menu_language": "Язык",
        "menu_reviews": "Отзывы",
        "choose_language": "Выберите язык:",
        "language_saved": "Язык сохранён.",
        "no_slots_available": "Сейчас свободных слотов нет.",
        "slot_selected": "Слот выбран.",
        "slot_unselected": "Слот снят с выбора.",
        "non_consecutive_error": "Можно выбрать только соседние слоты подряд.",
        "max_consecutive_error": "Можно выбрать не больше {max_slots} слотов подряд.",
        "slot_unavailable_error": "Этот слот уже недоступен. Выберите другое время.",
        "preview_title": "Проверьте вашу бронь:",
        "pickup_time": "Время выдачи: {time}",
        "confirm": "Подтвердить",
        "change": "Изменить",
        "booking_confirmed": "Бронь подтверждена.",
        "review_request": "Как вам заказ? Оставьте отзыв, пожалуйста.",
        "review_saved": "Спасибо! Отзыв сохранён.",
        "reviews_unavailable": "Раздел отзывов скоро будет доступен.",
    },
    "en": {
        "welcome": "Welcome to PranaNew. Choose an action from the menu.",
        "menu_free_slots": "Free slots",
        "menu_language": "Language",
        "menu_reviews": "Reviews",
        "choose_language": "Choose a language:",
        "language_saved": "Language saved.",
        "no_slots_available": "There are no free slots right now.",
        "slot_selected": "Slot selected.",
        "slot_unselected": "Slot removed from selection.",
        "non_consecutive_error": "You can select only neighboring consecutive slots.",
        "max_consecutive_error": "You can select no more than {max_slots} consecutive slots.",
        "slot_unavailable_error": "This slot is no longer available. Choose another time.",
        "preview_title": "Please check your booking:",
        "pickup_time": "Pickup time: {time}",
        "confirm": "Confirm",
        "change": "Change",
        "booking_confirmed": "Booking confirmed.",
        "review_request": "How was your order? Please leave a review.",
        "review_saved": "Thank you! Your review has been saved.",
        "reviews_unavailable": "The reviews section will be available soon.",
    },
    "sr": {
        "welcome": "Dobrodošli u PranaNew. Izaberite akciju iz menija.",
        "menu_free_slots": "Slobodni termini",
        "menu_language": "Jezik",
        "menu_reviews": "Recenzije",
        "choose_language": "Izaberite jezik:",
        "language_saved": "Jezik je sačuvan.",
        "no_slots_available": "Trenutno nema slobodnih termina.",
        "slot_selected": "Termin je izabran.",
        "slot_unselected": "Termin je uklonjen iz izbora.",
        "non_consecutive_error": "Možete izabrati samo susedne termine zaredom.",
        "max_consecutive_error": "Možete izabrati najviše {max_slots} termina zaredom.",
        "slot_unavailable_error": "Ovaj termin više nije dostupan. Izaberite drugo vreme.",
        "preview_title": "Proverite svoju rezervaciju:",
        "pickup_time": "Vreme preuzimanja: {time}",
        "confirm": "Potvrdi",
        "change": "Izmeni",
        "booking_confirmed": "Rezervacija je potvrđena.",
        "review_request": "Kako vam se dopala porudžbina? Ostavite recenziju, molimo.",
        "review_saved": "Hvala! Recenzija je sačuvana.",
        "reviews_unavailable": "Odeljak za recenzije uskoro će biti dostupan.",
    },
}


def normalize_language(language_code: str | None) -> str:
    """Normalize Telegram language_code to one of the supported languages."""

    if not language_code:
        return DEFAULT_LANGUAGE
    normalized = language_code.lower().replace("_", "-").split("-", maxsplit=1)[0]
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE


def t(key: str, language: str | None = DEFAULT_LANGUAGE, **kwargs: Any) -> str:
    """Translate a message key using a supported language with Russian fallback."""

    if key not in REQUIRED_KEYS:
        raise KeyError(f"Unknown i18n key: {key}")
    normalized_language = normalize_language(language)
    template = MESSAGES[normalized_language][key]
    if kwargs:
        return template.format(**kwargs)
    return template
