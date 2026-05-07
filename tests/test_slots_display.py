import unittest
from datetime import date, datetime, time, timezone

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.i18n import REQUIRED_KEYS, t
from bot.keyboards.client import available_slots_keyboard
from bot.routers.client import handle_free_slots_menu
from bot.services.slots import SLOT_CALLBACK_PREFIX, format_slot_label, list_available_slots
from bot.repositories.slots import SlotsRepository


class FakeUser:
    def __init__(self, *, id=42, username="alice", first_name="Alice", last_name="Tester", language_code="en-US"):
        self.id = id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.language_code = language_code


class FakeMessage:
    def __init__(self, *, from_user=None, text=""):
        self.from_user = from_user
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeDatabase:
    def __init__(self):
        self.users = {}
        self.fetch_result = []
        self.calls = []

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        if "INSERT INTO users" in query:
            tg_id, username, first_name, last_name, language = args
            existing = self.users.get(tg_id, {})
            self.users[tg_id] = {
                "tg_id": tg_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language": existing.get("language", language),
            }
        return "EXECUTE 1"

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return self.users.get(args[0])

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        user = self.users.get(args[0])
        return None if user is None else user.get("language")

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.fetch_result


class SlotsDisplayTest(unittest.IsolatedAsyncioTestCase):
    def test_task_031_i18n_contains_choose_slot_prompt_for_all_languages(self):
        self.assertIn("choose_slot", REQUIRED_KEYS)
        for language in ("ru", "en", "sr"):
            self.assertTrue(t("choose_slot", language))

    def test_task_031_formats_slot_button_labels_with_date_and_time(self):
        slot = {"slot_date": date(2026, 5, 8), "starts_at": time(14, 30)}

        self.assertEqual("08.05 14:30", format_slot_label(slot))

    def test_task_031_available_slots_keyboard_uses_inline_slot_callbacks(self):
        slots = [
            {"id": 10, "slot_date": date(2026, 5, 8), "starts_at": time(14, 0)},
            {"id": 11, "slot_date": date(2026, 5, 8), "starts_at": time(14, 10)},
            {"id": 12, "slot_date": date(2026, 5, 8), "starts_at": time(14, 20)},
            {"id": 13, "slot_date": date(2026, 5, 8), "starts_at": time(14, 30)},
        ]

        keyboard = available_slots_keyboard(slots)

        self.assertIsInstance(keyboard, InlineKeyboardMarkup)
        self.assertEqual([3, 1], [len(row) for row in keyboard.inline_keyboard])
        self.assertEqual("08.05 14:00", keyboard.inline_keyboard[0][0].text)
        self.assertEqual(f"{SLOT_CALLBACK_PREFIX}10", keyboard.inline_keyboard[0][0].callback_data)
        self.assertEqual(f"{SLOT_CALLBACK_PREFIX}13", keyboard.inline_keyboard[1][0].callback_data)

    async def test_task_031_slots_repository_lists_only_available_future_slots(self):
        db = FakeDatabase()
        db.fetch_result = [{"id": 10, "booked_count": 0}]
        repository = SlotsRepository(db)
        now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

        slots = await repository.list_available_future(now)

        self.assertEqual([{"id": 10, "booked_count": 0}], slots)
        query = db.calls[-1][1]
        self.assertIn("LEFT JOIN booking_slots", query)
        self.assertIn("LEFT JOIN bookings", query)
        self.assertIn("b.status IN ('active', 'completed')", query)
        self.assertIn("s.is_blocked = false", query)
        self.assertIn("s.start_time > $1", query)
        self.assertIn("HAVING COUNT(b.id) < s.capacity", query)
        self.assertIn("ORDER BY s.start_time ASC", query)
        self.assertEqual((now,), db.calls[-1][2])

    async def test_task_031_slots_service_returns_available_future_slots(self):
        db = FakeDatabase()
        db.fetch_result = [{"id": 10, "slot_date": date(2026, 5, 8), "starts_at": time(14, 0)}]
        now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

        slots = await list_available_slots(db, now=now)

        self.assertEqual(db.fetch_result, slots)
        self.assertEqual((now,), db.calls[-1][2])

    async def test_task_031_free_slots_menu_shows_inline_keyboard_when_slots_exist(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "en"}
        db.fetch_result = [
            {"id": 10, "slot_date": date(2026, 5, 8), "starts_at": time(14, 0)},
            {"id": 11, "slot_date": date(2026, 5, 8), "starts_at": time(14, 10)},
        ]
        message = FakeMessage(from_user=FakeUser(), text=t("menu_free_slots", "en"))

        await handle_free_slots_menu(message, db_pool=db)

        self.assertEqual(t("choose_slot", "en"), message.answers[0][0])
        markup = message.answers[0][1]["reply_markup"]
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        self.assertEqual(["08.05 14:00", "08.05 14:10"], [button.text for row in markup.inline_keyboard for button in row])

    async def test_task_031_free_slots_menu_keeps_main_menu_when_no_slots_exist(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "sr"}
        message = FakeMessage(from_user=FakeUser(), text=t("menu_free_slots", "sr"))

        await handle_free_slots_menu(message, db_pool=db)

        self.assertEqual(t("no_slots_available", "sr"), message.answers[0][0])
        self.assertIsInstance(message.answers[0][1]["reply_markup"], ReplyKeyboardMarkup)


if __name__ == "__main__":
    unittest.main()
