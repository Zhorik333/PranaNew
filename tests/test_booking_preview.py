import unittest
from datetime import date, time

from aiogram.types import InlineKeyboardMarkup

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.keyboards.client import available_slots_keyboard, booking_preview_keyboard
from bot.routers.client import handle_booking_preview, handle_booking_preview_change
from bot.services.slots import (
    BOOKING_PREVIEW_CALLBACK_PREFIX,
    BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX,
    BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX,
    SLOT_CALLBACK_PREFIX,
    build_booking_preview_callback_data,
    format_booking_preview_text,
    pickup_time,
)


class FakeUser:
    def __init__(self, *, id=42):
        self.id = id


class FakeCallbackMessage:
    def __init__(self):
        self.edited_texts = []
        self.edited_reply_markups = []

    async def edit_text(self, text, **kwargs):
        self.edited_texts.append((text, kwargs))

    async def edit_reply_markup(self, **kwargs):
        self.edited_reply_markups.append(kwargs)


class FakeCallback:
    def __init__(self, *, data, from_user=None, message=None):
        self.data = data
        self.from_user = from_user or FakeUser()
        self.message = message or FakeCallbackMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class FakeDatabase:
    def __init__(self):
        self.fetch_result = []
        self.language = "ru"
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.fetch_result

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return self.language


def slot(slot_id, hour, minute, *, duration=10):
    return {
        "id": slot_id,
        "slot_date": date(2026, 5, 8),
        "starts_at": time(hour, minute),
        "duration_minutes": duration,
    }


class BookingPreviewTest(unittest.IsolatedAsyncioTestCase):
    def test_task_033_i18n_contains_preview_keys_for_all_languages(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("preview_title", language))
            self.assertTrue(t("pickup_time", language, time="14:10"))
            self.assertTrue(t("confirm", language))
            self.assertTrue(t("change", language))
            self.assertTrue(t("preview_empty_selection_error", language))
            self.assertTrue(t("done", language))

    def test_task_033_pickup_time_is_last_selected_slot(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        self.assertEqual("14:10", pickup_time(slots, [10, 11]).strftime("%H:%M"))
        self.assertEqual("14:20", pickup_time(slots, [12, 10, 11]).strftime("%H:%M"))

    def test_task_033_preview_text_shows_selected_slots_and_pickup_time(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        text = format_booking_preview_text(slots, [10, 11], "ru")

        self.assertIn(t("preview_title", "ru"), text)
        self.assertIn("08.05 14:00", text)
        self.assertIn("08.05 14:10", text)
        self.assertNotIn("08.05 14:20", text)
        self.assertIn(t("pickup_time", "ru", time="14:10"), text)

    def test_task_033_slots_keyboard_has_done_button_when_slots_are_selected(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10)]

        keyboard = available_slots_keyboard(slots, selected_slot_ids=[10, 11], language="ru")

        done_button = keyboard.inline_keyboard[-1][0]
        self.assertEqual(t("done", "ru"), done_button.text)
        self.assertEqual(f"{BOOKING_PREVIEW_CALLBACK_PREFIX}10,11", done_button.callback_data)

    def test_task_033_slots_keyboard_hides_done_button_without_selection(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10)]

        keyboard = available_slots_keyboard(slots, selected_slot_ids=[], language="ru")

        flattened = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertNotIn(t("done", "ru"), flattened)

    def test_task_033_preview_keyboard_has_confirm_and_change_buttons(self):
        keyboard = booking_preview_keyboard([10, 11], language="ru")

        self.assertIsInstance(keyboard, InlineKeyboardMarkup)
        self.assertEqual(t("confirm", "ru"), keyboard.inline_keyboard[0][0].text)
        self.assertEqual(f"{BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX}10,11", keyboard.inline_keyboard[0][0].callback_data)
        self.assertEqual(t("change", "ru"), keyboard.inline_keyboard[0][1].text)
        self.assertEqual(f"{BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX}10,11", keyboard.inline_keyboard[0][1].callback_data)

    def test_task_033_build_preview_callback_data_rejects_empty_selection(self):
        with self.assertRaises(ValueError):
            build_booking_preview_callback_data([])

    async def test_task_033_preview_callback_edits_message_to_preview(self):
        db = FakeDatabase()
        db.fetch_result = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]
        message = FakeCallbackMessage()
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CALLBACK_PREFIX}10,11", message=message)

        await handle_booking_preview(callback, db_pool=db)

        self.assertEqual((None, {}), callback.answers[0])
        preview_text, kwargs = message.edited_texts[0]
        self.assertIn(t("preview_title", "ru"), preview_text)
        self.assertIn(t("pickup_time", "ru", time="14:10"), preview_text)
        markup = kwargs["reply_markup"]
        self.assertEqual(t("confirm", "ru"), markup.inline_keyboard[0][0].text)
        self.assertEqual(f"{BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX}10,11", markup.inline_keyboard[0][1].callback_data)

    async def test_task_045_preview_callback_alerts_when_selection_exceeds_limit(self):
        db = FakeDatabase()
        db.fetch_result = [
            slot(10, 14, 0),
            slot(11, 14, 10),
            slot(12, 14, 20),
            slot(13, 14, 30),
            slot(14, 14, 40),
            slot(15, 14, 50),
        ]
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CALLBACK_PREFIX}10,11,12,13,14,15")

        await handle_booking_preview(callback, db_pool=db)

        self.assertEqual((t("max_consecutive_error", "ru", max_slots=5), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_texts)

    async def test_task_033_change_callback_returns_to_slot_selection_with_same_selection(self):
        db = FakeDatabase()
        db.fetch_result = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]
        message = FakeCallbackMessage()
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX}10,11", message=message)

        await handle_booking_preview_change(callback, db_pool=db)

        self.assertEqual((None, {}), callback.answers[0])
        text, kwargs = message.edited_texts[0]
        self.assertEqual(t("choose_slot", "ru"), text)
        markup = kwargs["reply_markup"]
        self.assertEqual("✅ 08.05 14:00", markup.inline_keyboard[0][0].text)
        self.assertEqual("✅ 08.05 14:10", markup.inline_keyboard[0][1].text)
        self.assertEqual(f"{SLOT_CALLBACK_PREFIX}12|10,11", markup.inline_keyboard[0][2].callback_data)


if __name__ == "__main__":
    unittest.main()
