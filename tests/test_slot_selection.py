import unittest
from datetime import date, time

from aiogram.types import InlineKeyboardMarkup

from bot.i18n import t
from bot.keyboards.client import available_slots_keyboard
from bot.routers.client import handle_slot_selected
from bot.services.slots import (
    SLOT_CALLBACK_PREFIX,
    SlotSelectionError,
    parse_slot_callback_data,
    toggle_slot_selection,
)


class FakeUser:
    def __init__(self, *, id=42):
        self.id = id


class FakeCallbackMessage:
    def __init__(self):
        self.edited_reply_markups = []

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


class SlotSelectionTest(unittest.IsolatedAsyncioTestCase):
    def test_task_032_slot_keyboard_marks_selected_slots_and_encodes_selection(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        keyboard = available_slots_keyboard(slots, selected_slot_ids=[10, 11])

        self.assertIsInstance(keyboard, InlineKeyboardMarkup)
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        self.assertEqual("✅ 08.05 14:00", buttons[0].text)
        self.assertEqual("✅ 08.05 14:10", buttons[1].text)
        self.assertEqual("08.05 14:20", buttons[2].text)
        self.assertEqual(f"{SLOT_CALLBACK_PREFIX}10|10,11", buttons[0].callback_data)
        self.assertEqual(f"{SLOT_CALLBACK_PREFIX}12|10,11", buttons[2].callback_data)

    def test_task_032_parse_slot_callback_data(self):
        self.assertEqual((12, [10, 11]), parse_slot_callback_data("slot:12|10,11"))
        self.assertEqual((12, []), parse_slot_callback_data("slot:12|"))
        with self.assertRaises(ValueError):
            parse_slot_callback_data("language:ru")

    def test_task_032_selects_first_slot_and_neighboring_slot(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        self.assertEqual([10], toggle_slot_selection(slots, selected_slot_ids=[], clicked_slot_id=10))
        self.assertEqual([10, 11], toggle_slot_selection(slots, selected_slot_ids=[10], clicked_slot_id=11))

    def test_task_032_rejects_non_consecutive_slot_selection(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        with self.assertRaisesRegex(SlotSelectionError, "non_consecutive"):
            toggle_slot_selection(slots, selected_slot_ids=[10], clicked_slot_id=12)

    def test_task_032_rejects_selection_above_max_consecutive(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        with self.assertRaisesRegex(SlotSelectionError, "max_consecutive"):
            toggle_slot_selection(slots, selected_slot_ids=[10, 11], clicked_slot_id=12, max_consecutive=2)

    def test_task_032_deselects_edge_slot_but_rejects_middle_deselect(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        self.assertEqual([10, 11], toggle_slot_selection(slots, selected_slot_ids=[10, 11, 12], clicked_slot_id=12))
        with self.assertRaisesRegex(SlotSelectionError, "non_consecutive"):
            toggle_slot_selection(slots, selected_slot_ids=[10, 11, 12], clicked_slot_id=11)

    def test_task_032_rejects_unavailable_clicked_slot(self):
        slots = [slot(10, 14, 0), slot(11, 14, 10)]

        with self.assertRaisesRegex(SlotSelectionError, "slot_unavailable"):
            toggle_slot_selection(slots, selected_slot_ids=[10], clicked_slot_id=99)

    async def test_task_032_slot_callback_updates_keyboard_with_selected_marker(self):
        db = FakeDatabase()
        db.fetch_result = [slot(10, 14, 0), slot(11, 14, 10)]
        message = FakeCallbackMessage()
        callback = FakeCallback(data="slot:10|", message=message)

        await handle_slot_selected(callback, db_pool=db)

        self.assertEqual((t("slot_selected", "ru"), {"show_alert": False}), callback.answers[0])
        markup = message.edited_reply_markups[0]["reply_markup"]
        self.assertEqual("✅ 08.05 14:00", markup.inline_keyboard[0][0].text)
        self.assertEqual(f"{SLOT_CALLBACK_PREFIX}11|10", markup.inline_keyboard[0][1].callback_data)

    async def test_task_032_slot_callback_alerts_on_non_consecutive_selection(self):
        db = FakeDatabase()
        db.fetch_result = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]
        callback = FakeCallback(data="slot:12|10")

        await handle_slot_selected(callback, db_pool=db)

        self.assertEqual((t("non_consecutive_error", "ru"), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_reply_markups)
    async def test_task_032_slot_callback_alerts_on_max_consecutive_selection(self):
        db = FakeDatabase()
        db.fetch_result = [
            slot(10, 14, 0),
            slot(11, 14, 10),
            slot(12, 14, 20),
            slot(13, 14, 30),
            slot(14, 14, 40),
            slot(15, 14, 50),
        ]
        callback = FakeCallback(data="slot:15|10,11,12,13,14")

        await handle_slot_selected(callback, db_pool=db)

        self.assertEqual((t("max_consecutive_error", "ru", max_slots=5), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_reply_markups)
    async def test_task_032_slot_callback_uses_saved_language_for_alerts(self):
        db = FakeDatabase()
        db.language = "en"
        db.fetch_result = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]
        callback = FakeCallback(data="slot:12|10")

        await handle_slot_selected(callback, db_pool=db)

        self.assertEqual((t("non_consecutive_error", "en"), {"show_alert": True}), callback.answers[0])


if __name__ == "__main__":
    unittest.main()
