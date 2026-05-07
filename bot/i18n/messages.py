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
    "choose_slot",
    "slot_selected",
    "slot_unselected",
    "non_consecutive_error",
    "max_consecutive_error",
    "slot_unavailable_error",
    "done",
    "preview_title",
    "pickup_time",
    "confirm",
    "change",
    "preview_empty_selection_error",
    "booking_confirmed",
    "booking_unavailable",
    "booking_already_confirmed",
    "cancel_booking",
    "booking_cancelled",
    "booking_cancel_unavailable",
    "complete_booking",
    "booking_completed",
    "booking_complete_unavailable",
    "admin_only",
    "leave_review",
    "review_request",
    "admin_new_booking",
    "admin_booking_cancelled",
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
        "choose_slot": "Выберите свободный слот:",
        "slot_selected": "Слот выбран.",
        "slot_unselected": "Слот снят с выбора.",
        "non_consecutive_error": "Можно выбрать только соседние слоты подряд.",
        "max_consecutive_error": "Можно выбрать не больше {max_slots} слотов подряд.",
        "slot_unavailable_error": "Этот слот уже недоступен. Выберите другое время.",
        "done": "Готово",
        "preview_title": "Проверьте вашу бронь:",
        "pickup_time": "Время выдачи: {time}",
        "confirm": "Подтвердить",
        "change": "Изменить",
        "preview_empty_selection_error": "Сначала выберите хотя бы один слот.",
        "booking_confirmed": "Бронь #{booking_id} подтверждена.",
        "booking_unavailable": "Эти слоты уже недоступны. Пожалуйста, выберите другое время.",
        "booking_already_confirmed": "Бронь #{booking_id} уже подтверждена.",
        "cancel_booking": "Отменить бронь",
        "booking_cancelled": "Бронь #{booking_id} отменена.",
        "booking_cancel_unavailable": "Эту бронь уже нельзя отменить.",
        "complete_booking": "Заказ выдан",
        "booking_completed": "Бронь #{booking_id} отмечена как выданная.",
        "booking_complete_unavailable": "Эту бронь нельзя завершить.",
        "admin_only": "Это действие доступно только администратору.",
        "leave_review": "Оставить отзыв",
        "review_request": "Как вам заказ? Оставьте отзыв, пожалуйста.",
        "admin_new_booking": "Новая бронь",
        "admin_booking_cancelled": "Бронь отменена пользователем",
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
        "choose_slot": "Choose a free slot:",
        "slot_selected": "Slot selected.",
        "slot_unselected": "Slot removed from selection.",
        "non_consecutive_error": "You can select only neighboring consecutive slots.",
        "max_consecutive_error": "You can select no more than {max_slots} consecutive slots.",
        "slot_unavailable_error": "This slot is no longer available. Choose another time.",
        "done": "Done",
        "preview_title": "Please check your booking:",
        "pickup_time": "Pickup time: {time}",
        "confirm": "Confirm",
        "change": "Change",
        "preview_empty_selection_error": "Please select at least one slot first.",
        "booking_confirmed": "Booking #{booking_id} confirmed.",
        "booking_unavailable": "These slots are no longer available. Please choose another time.",
        "booking_already_confirmed": "Booking #{booking_id} is already confirmed.",
        "cancel_booking": "Cancel booking",
        "booking_cancelled": "Booking #{booking_id} cancelled.",
        "booking_cancel_unavailable": "This booking can no longer be cancelled.",
        "complete_booking": "Mark completed",
        "booking_completed": "Booking #{booking_id} marked as completed.",
        "booking_complete_unavailable": "This booking cannot be completed.",
        "admin_only": "This action is available only to admins.",
        "leave_review": "Leave a review",
        "review_request": "How was your order? Please leave a review.",
        "admin_new_booking": "New booking",
        "admin_booking_cancelled": "Booking cancelled by user",
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
        "choose_slot": "Izaberite slobodan termin:",
        "slot_selected": "Termin je izabran.",
        "slot_unselected": "Termin je uklonjen iz izbora.",
        "non_consecutive_error": "Možete izabrati samo susedne termine zaredom.",
        "max_consecutive_error": "Možete izabrati najviše {max_slots} termina zaredom.",
        "slot_unavailable_error": "Ovaj termin više nije dostupan. Izaberite drugo vreme.",
        "done": "Gotovo",
        "preview_title": "Proverite svoju rezervaciju:",
        "pickup_time": "Vreme preuzimanja: {time}",
        "confirm": "Potvrdi",
        "change": "Izmeni",
        "preview_empty_selection_error": "Prvo izaberite bar jedan termin.",
        "booking_confirmed": "Rezervacija #{booking_id} je potvrđena.",
        "booking_unavailable": "Ovi termini više nisu dostupni. Izaberite drugo vreme.",
        "booking_already_confirmed": "Rezervacija #{booking_id} je već potvrđena.",
        "cancel_booking": "Otkaži rezervaciju",
        "booking_cancelled": "Rezervacija #{booking_id} je otkazana.",
        "booking_cancel_unavailable": "Ovu rezervaciju više nije moguće otkazati.",
        "complete_booking": "Označi kao završeno",
        "booking_completed": "Rezervacija #{booking_id} je označena kao završena.",
        "booking_complete_unavailable": "Ovu rezervaciju nije moguće završiti.",
        "admin_only": "Ova akcija je dostupna samo administratorima.",
        "leave_review": "Ostavi recenziju",
        "review_request": "Kako vam se dopala porudžbina? Ostavite recenziju, molimo.",
        "admin_new_booking": "Nova rezervacija",
        "admin_booking_cancelled": "Rezervaciju je otkazao korisnik",
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
