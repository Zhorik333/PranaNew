import unittest

from aiogram.types import ReplyKeyboardMarkup

from bot.i18n import REQUIRED_KEYS, t
from bot.keyboards.client import main_menu_keyboard
from bot.routers.client import (
    FREE_SLOTS_MENU_TEXTS,
    REVIEWS_MENU_TEXTS,
    handle_free_slots_menu,
    handle_reviews_menu,
    handle_start,
)


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
        elif "SET language" in query:
            language, tg_id = args
            self.users.setdefault(tg_id, {"tg_id": tg_id})["language"] = language
        return "EXECUTE 1"

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return self.users.get(args[0])

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        user = self.users.get(args[0])
        return None if user is None else user.get("language")


class ClientMainMenuTest(unittest.IsolatedAsyncioTestCase):
    def test_task_030_main_menu_keyboard_has_expected_localized_layout(self):
        keyboard = main_menu_keyboard("ru")

        self.assertIsInstance(keyboard, ReplyKeyboardMarkup)
        self.assertTrue(keyboard.resize_keyboard)
        self.assertTrue(keyboard.is_persistent)
        self.assertEqual(
            [
                [t("menu_free_slots", "ru")],
                [t("menu_language", "ru"), t("menu_reviews", "ru")],
            ],
            [[button.text for button in row] for row in keyboard.keyboard],
        )

    async def test_task_030_start_saves_new_user_and_shows_full_menu_in_detected_language(self):
        db = FakeDatabase()
        message = FakeMessage(from_user=FakeUser(language_code="sr-Latn"))

        await handle_start(message, db_pool=db)

        self.assertEqual("sr", db.users[42]["language"])
        self.assertEqual(t("welcome", "sr"), message.answers[0][0])
        markup = message.answers[0][1]["reply_markup"]
        self.assertEqual(
            [t("menu_free_slots", "sr"), t("menu_language", "sr"), t("menu_reviews", "sr")],
            [button.text for row in markup.keyboard for button in row],
        )

    async def test_task_030_start_uses_saved_language_for_existing_user_menu(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "en"}
        message = FakeMessage(from_user=FakeUser(language_code="ru-RU"))

        await handle_start(message, db_pool=db)

        self.assertEqual("en", db.users[42]["language"])
        self.assertEqual(t("welcome", "en"), message.answers[0][0])
        markup_texts = [button.text for row in message.answers[0][1]["reply_markup"].keyboard for button in row]
        self.assertEqual([t("menu_free_slots", "en"), t("menu_language", "en"), t("menu_reviews", "en")], markup_texts)

    async def test_task_030_free_slots_menu_button_leads_to_localized_placeholder_screen(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "en"}
        message = FakeMessage(from_user=FakeUser(), text=t("menu_free_slots", "en"))

        await handle_free_slots_menu(message, db_pool=db)

        self.assertEqual(t("no_slots_available", "en"), message.answers[0][0])
        self.assertIsInstance(message.answers[0][1]["reply_markup"], ReplyKeyboardMarkup)

    async def test_task_030_reviews_menu_button_leads_to_localized_placeholder_screen(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "sr"}
        message = FakeMessage(from_user=FakeUser(), text=t("menu_reviews", "sr"))

        await handle_reviews_menu(message, db_pool=db)

        self.assertEqual(t("reviews_unavailable", "sr"), message.answers[0][0])
        self.assertIsInstance(message.answers[0][1]["reply_markup"], ReplyKeyboardMarkup)

    def test_task_030_router_filters_cover_all_localized_menu_buttons(self):
        self.assertEqual({t("menu_free_slots", language) for language in ("ru", "en", "sr")}, FREE_SLOTS_MENU_TEXTS)
        self.assertEqual({t("menu_reviews", language) for language in ("ru", "en", "sr")}, REVIEWS_MENU_TEXTS)
        self.assertIn("reviews_unavailable", REQUIRED_KEYS)


if __name__ == "__main__":
    unittest.main()
