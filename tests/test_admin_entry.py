import inspect
import unittest

from aiogram.types import ReplyKeyboardMarkup

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.keyboards.admin import admin_menu_keyboard
from bot.routers.admin import create_admin_router, handle_admin_entry, handle_chat_id


class FakeChat:
    def __init__(self, id):
        self.id = id


class FakeMessage:
    def __init__(self, *, chat_id):
        self.chat = FakeChat(chat_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


def make_config(admin_chat_id=-100123):
    return Config(
        **{
            "bot_" + "token": "***",
            "database_url": "postgresql://prananew:***@127.0.0.1:5432/prananew",
            "admin_chat_id": admin_chat_id,
        }
    )


class AdminEntryTest(unittest.IsolatedAsyncioTestCase):
    def test_task_070_i18n_contains_admin_entry_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("admin_menu_title", language))
            self.assertTrue(t("admin_chat_id", language, chat_id=-100123))
            self.assertTrue(t("admin_menu_generate_slots", language))
            self.assertTrue(t("admin_menu_booked_slots", language))
            self.assertTrue(t("admin_menu_active_date", language))
            self.assertTrue(t("admin_menu_reviews", language))

    def test_task_070_admin_menu_keyboard_is_persistent_and_compact(self):
        keyboard = admin_menu_keyboard(language="ru")

        self.assertIsInstance(keyboard, ReplyKeyboardMarkup)
        self.assertTrue(keyboard.resize_keyboard)
        self.assertTrue(keyboard.is_persistent)
        labels = [[button.text for button in row] for row in keyboard.keyboard]
        self.assertEqual(
            [
                [t("admin_menu_generate_slots", "ru"), t("admin_menu_booked_slots", "ru")],
                [t("admin_menu_active_date", "ru"), t("admin_menu_reviews", "ru")],
            ],
            labels,
        )

    async def test_task_070_admin_command_opens_menu_only_in_admin_chat(self):
        admin_message = FakeMessage(chat_id=-100123)
        non_admin_message = FakeMessage(chat_id=42)
        config = make_config(admin_chat_id=-100123)

        await handle_admin_entry(admin_message, config)
        await handle_admin_entry(non_admin_message, config)

        self.assertEqual(t("admin_menu_title", "ru"), admin_message.answers[0][0])
        self.assertIsInstance(admin_message.answers[0][1]["reply_markup"], ReplyKeyboardMarkup)
        self.assertEqual(t("admin_only", "ru"), non_admin_message.answers[0][0])
        self.assertNotIn("reply_markup", non_admin_message.answers[0][1])

    async def test_task_070_chatid_command_returns_current_chat_id(self):
        message = FakeMessage(chat_id=-100999)

        await handle_chat_id(message)

        self.assertEqual(t("admin_chat_id", "ru", chat_id=-100999), message.answers[0][0])

    def test_task_070_admin_router_registers_admin_and_chatid_but_not_start(self):
        router = create_admin_router()
        source = inspect.getsource(create_admin_router)

        self.assertEqual("admin", router.name)
        self.assertIn('Command("admin")', source)
        self.assertIn('Command("chatid")', source)
        self.assertNotIn("CommandStart", source)
        self.assertNotIn('Command("start")', source)
        self.assertNotIn("Command('start')", source)


if __name__ == "__main__":
    unittest.main()
