import unittest

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.i18n import t
from bot.keyboards.client import language_selection_keyboard, main_menu_keyboard
from bot.routers.client import handle_language_menu, handle_language_selected, handle_start
from bot.services.language import get_user_language, save_user_language


class FakeUser:
    def __init__(
        self,
        *,
        id=42,
        username="alice",
        first_name="Alice",
        last_name="Tester",
        language_code="en-US",
    ):
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


class FakeCallbackQuery:
    def __init__(self, *, from_user=None, data="language:sr"):
        self.from_user = from_user
        self.data = data
        self.message = FakeMessage(from_user=from_user)
        self.answered = []

    async def answer(self, text=None, **kwargs):
        self.answered.append((text, kwargs))


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


class LanguageSelectionFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_task_011_start_creates_new_user_from_telegram_language_and_shows_menu(self):
        db = FakeDatabase()
        message = FakeMessage(from_user=FakeUser(language_code="en-US"))

        await handle_start(message, db_pool=db)

        self.assertEqual("en", db.users[42]["language"])
        self.assertEqual(t("welcome", "en"), message.answers[0][0])
        self.assertIsInstance(message.answers[0][1]["reply_markup"], ReplyKeyboardMarkup)
        button_texts = [
            button.text
            for row in message.answers[0][1]["reply_markup"].keyboard
            for button in row
        ]
        self.assertIn(t("menu_language", "en"), button_texts)

    async def test_task_011_start_preserves_saved_language_for_existing_user(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "sr"}
        message = FakeMessage(from_user=FakeUser(language_code="en-US"))

        await handle_start(message, db_pool=db)

        self.assertEqual("sr", db.users[42]["language"])
        self.assertEqual(t("welcome", "sr"), message.answers[0][0])

    async def test_task_011_language_button_opens_language_choice_keyboard_in_saved_language(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "sr"}
        message = FakeMessage(from_user=FakeUser(), text=t("menu_language", "sr"))

        await handle_language_menu(message, db_pool=db)

        self.assertEqual(t("choose_language", "sr"), message.answers[0][0])
        self.assertIsInstance(message.answers[0][1]["reply_markup"], InlineKeyboardMarkup)
        callback_data = [
            button.callback_data
            for row in message.answers[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertEqual(["language:ru", "language:en", "language:sr"], callback_data)

    async def test_task_011_language_callback_saves_language_and_next_message_uses_it(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "ru"}
        callback = FakeCallbackQuery(from_user=FakeUser(), data="language:en")

        await handle_language_selected(callback, db_pool=db)
        next_message = FakeMessage(from_user=FakeUser(language_code="ru-RU"))
        await handle_start(next_message, db_pool=db)

        self.assertEqual("en", db.users[42]["language"])
        self.assertEqual(t("language_saved", "en"), callback.message.answers[0][0])
        self.assertEqual(t("welcome", "en"), next_message.answers[0][0])

    async def test_task_011_invalid_language_callback_falls_back_to_russian(self):
        db = FakeDatabase()
        callback = FakeCallbackQuery(from_user=FakeUser(), data="language:de")

        await handle_language_selected(callback, db_pool=db)

        self.assertEqual("ru", db.users[42]["language"])
        self.assertEqual(t("language_saved", "ru"), callback.message.answers[0][0])

    async def test_task_011_language_service_gets_and_saves_supported_language(self):
        db = FakeDatabase()
        db.users[42] = {"tg_id": 42, "language": "sr"}

        language = await get_user_language(db, 42, default="en")
        await save_user_language(db, 42, "en-US")

        self.assertEqual("sr", language)
        self.assertEqual("en", db.users[42]["language"])

    def test_task_011_keyboards_are_localized(self):
        menu = main_menu_keyboard("sr")
        language_keyboard = language_selection_keyboard()

        menu_texts = [button.text for row in menu.keyboard for button in row]
        self.assertEqual(
            [t("menu_free_slots", "sr"), t("menu_language", "sr"), t("menu_reviews", "sr")],
            menu_texts,
        )
        self.assertEqual(
            ["Русский", "English", "Srpski"],
            [
                button.text
                for row in language_keyboard.inline_keyboard
                for button in row
            ],
        )


if __name__ == "__main__":
    unittest.main()
