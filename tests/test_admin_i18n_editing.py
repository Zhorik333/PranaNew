import unittest

from bot.config import Config
from bot.i18n import REQUIRED_KEYS, SUPPORTED_LANGUAGES, t
from bot.keyboards.admin import admin_menu_keyboard
from bot.repositories.i18n_texts import I18nTextsRepository
from bot.routers.admin import (
    handle_admin_clear_text,
    handle_admin_get_text,
    handle_admin_i18n_menu,
    handle_admin_set_text,
)
from bot.services.admin_i18n import (
    AdminI18nError,
    AdminI18nService,
    format_i18n_text_report,
    parse_clear_text_command,
    parse_get_text_command,
    parse_set_text_command,
    translate_with_overrides,
)


class FakeDatabase:
    def __init__(self):
        self.calls = []
        self.fetchrow_result = None
        self.fetch_result = []

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "OK"

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_result

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.fetch_result


class Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return Acquire(self.connection)


class FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class FakeMessage:
    def __init__(self, text, chat_id=12345):
        self.text = text
        self.chat = FakeChat(chat_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


def config(admin_chat_id=12345):
    return Config(
        bot_token="fake",
        database_url="postgresql://example/example",
        admin_chat_id=admin_chat_id,
    )


class AdminI18nEditingTest(unittest.IsolatedAsyncioTestCase):
    def test_task_075_parses_text_edit_commands(self):
        self.assertEqual(("ru", "welcome", "Привет всем"), parse_set_text_command("/set_text ru welcome Привет всем"))
        self.assertEqual(("en", "welcome"), parse_get_text_command("/get_text en welcome"))
        self.assertEqual(("sr", "welcome"), parse_clear_text_command("/clear_text sr welcome"))

        with self.assertRaises(AdminI18nError):
            parse_set_text_command("/set_text ru welcome")
        with self.assertRaises(AdminI18nError):
            parse_set_text_command("/set_text de welcome Hallo")
        with self.assertRaises(AdminI18nError):
            parse_set_text_command("/set_text ru unknown_key Текст")
        with self.assertRaises(AdminI18nError):
            parse_get_text_command("/get_text ru")
        with self.assertRaises(AdminI18nError):
            parse_clear_text_command("/clear_text ru unknown_key")

    async def test_task_075_repository_upserts_reads_lists_and_deletes_i18n_texts(self):
        db = FakeDatabase()
        db.fetchrow_result = {"language": "ru", "key": "welcome", "value": "Привет"}
        db.fetch_result = [{"language": "ru", "key": "welcome", "value": "Привет"}]
        repo = I18nTextsRepository(db)

        await repo.set_text("ru", "welcome", "Привет")
        row = await repo.get_text("ru", "welcome")
        rows = await repo.list_texts(language="ru")
        await repo.delete_text("ru", "welcome")

        self.assertEqual("Привет", row["value"])
        self.assertEqual(db.fetch_result, rows)
        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("INSERT INTO i18n_texts", queries)
        self.assertIn("ON CONFLICT", queries)
        self.assertIn("SELECT language, key, value", queries)
        self.assertIn("DELETE FROM i18n_texts", queries)
        self.assertNotIn("{", queries)
        self.assertEqual(("ru", "welcome", "Привет"), db.calls[0][2])

    async def test_task_075_service_validates_and_manages_custom_texts(self):
        db = FakeDatabase()
        pool = FakePool(db)
        service = AdminI18nService(pool)

        await service.set_text("ru", "welcome", "Новый привет")
        db.fetchrow_result = {"language": "ru", "key": "welcome", "value": "Новый привет"}
        text = await service.get_text("ru", "welcome")
        await service.clear_text("ru", "welcome")

        self.assertEqual("Новый привет", text["value"])
        with self.assertRaises(AdminI18nError):
            await service.set_text("de", "welcome", "Hallo")
        with self.assertRaises(AdminI18nError):
            await service.set_text("ru", "unknown_key", "Текст")
        with self.assertRaises(AdminI18nError):
            await service.set_text("ru", "welcome", "")

    def test_task_075_formats_report_with_html_escaping_and_fallback(self):
        custom = {"language": "ru", "key": "welcome", "value": "<b>Привет</b>"}
        report = format_i18n_text_report(custom, language="ru")
        self.assertIn("&lt;b&gt;Привет&lt;/b&gt;", report)
        self.assertIn("welcome", report)

        fallback_report = format_i18n_text_report(None, language="ru", key="welcome", text=t("welcome", "ru"))
        self.assertIn("словарь", fallback_report.lower())
        self.assertIn(t("welcome", "ru"), fallback_report)

    async def test_task_075_handlers_require_admin_chat_and_answer_reports(self):
        db = FakeDatabase()
        pool = FakePool(db)
        cfg = config()

        non_admin = FakeMessage("/set_text ru welcome Привет", chat_id=999)
        await handle_admin_set_text(non_admin, pool, cfg)
        self.assertIn(t("admin_only", "ru"), non_admin.answers[-1][0])
        self.assertEqual([], db.calls)

        set_msg = FakeMessage("/set_text ru welcome Привет")
        await handle_admin_set_text(set_msg, pool, cfg)
        self.assertIn(t("admin_i18n_text_updated", "ru"), set_msg.answers[-1][0])

        db.fetchrow_result = {"language": "ru", "key": "welcome", "value": "Привет"}
        get_msg = FakeMessage("/get_text ru welcome")
        await handle_admin_get_text(get_msg, pool, cfg)
        self.assertIn("Привет", get_msg.answers[-1][0])

        clear_msg = FakeMessage("/clear_text ru welcome")
        await handle_admin_clear_text(clear_msg, pool, cfg)
        self.assertIn(t("admin_i18n_text_cleared", "ru"), clear_msg.answers[-1][0])

        menu_msg = FakeMessage(t("admin_menu_i18n", "ru"))
        await handle_admin_i18n_menu(menu_msg, pool, cfg)
        self.assertIn("/set_text", menu_msg.answers[-1][0])

        labels = [[button.text for button in row] for row in admin_menu_keyboard("ru").keyboard]
        flat_labels = [label for row in labels for label in row]
        self.assertIn(t("admin_menu_reviews", "ru"), flat_labels)
        self.assertIn(t("admin_menu_i18n", "ru"), flat_labels)

    async def test_task_075_translate_with_overrides_uses_custom_text_then_fallback(self):
        db = FakeDatabase()
        pool = FakePool(db)
        db.fetchrow_result = {"language": "ru", "key": "welcome", "value": "Привет, {name}!"}

        custom = await translate_with_overrides(pool, "welcome", "ru", name="Анна")
        db.fetchrow_result = None
        fallback = await translate_with_overrides(pool, "welcome", "ru")

        self.assertEqual("Привет, Анна!", custom)
        self.assertEqual(t("welcome", "ru"), fallback)

    def test_task_075_i18n_contains_admin_editing_keys(self):
        expected = {
            "admin_i18n_help",
            "admin_menu_i18n",
            "admin_i18n_text_updated",
            "admin_i18n_text_cleared",
            "admin_i18n_text_title",
            "admin_i18n_text_source_custom",
            "admin_i18n_text_source_default",
            "admin_i18n_command_error",
        }
        self.assertTrue(expected.issubset(set(REQUIRED_KEYS)))
        for language in SUPPORTED_LANGUAGES:
            for key in expected:
                self.assertIsInstance(t(key, language), str)
                self.assertTrue(t(key, language))
