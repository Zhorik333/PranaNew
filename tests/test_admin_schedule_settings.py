import unittest
from datetime import date, time

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.settings import SettingsRepository
from bot.routers.admin import (
    handle_admin_active_date_menu,
    handle_admin_clear_active_date,
    handle_admin_schedule_settings,
    handle_admin_set_active_date,
    handle_admin_set_schedule,
    handle_admin_show_active_date,
)
from bot.services.admin_schedule import (
    AdminScheduleError,
    AdminScheduleService,
    ScheduleSettings,
    format_active_date_report,
    format_schedule_settings_report,
    parse_set_active_date_command,
    parse_set_schedule_command,
)


class FakeAcquire:
    def __init__(self, pool):
        self.pool = pool

    async def __aenter__(self):
        self.pool.connection.events.append("acquire_enter")
        return self.pool.connection

    async def __aexit__(self, exc_type, exc, tb):
        self.pool.connection.events.append("acquire_exit")
        return False


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        self.connection.events.append("acquire_called")
        return FakeAcquire(self)


class FakeConnection:
    def __init__(self):
        self.events = []
        self.calls = []
        self.values = {}

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        if "INSERT INTO settings" in query:
            self.values[args[0]] = args[1]
        if "DELETE FROM settings" in query:
            self.values.pop(args[0], None)
        return "EXECUTE 1"

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return self.values.get(args[0])


class FakeChat:
    def __init__(self, id):
        self.id = id


class FakeMessage:
    def __init__(self, *, chat_id=-100123, text=""):
        self.chat = FakeChat(chat_id)
        self.text = text
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


class AdminScheduleSettingsTest(unittest.IsolatedAsyncioTestCase):
    def test_task_074_i18n_contains_admin_schedule_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("admin_schedule_help", language))
            self.assertTrue(t("admin_schedule_settings_title", language))
            self.assertTrue(t("admin_active_date_current", language, active_date="2026-05-08"))
            self.assertTrue(t("admin_active_date_not_set", language))
            self.assertTrue(t("admin_active_date_updated", language, active_date="2026-05-08"))
            self.assertTrue(t("admin_active_date_cleared", language))
            self.assertTrue(t("admin_schedule_updated", language))
            self.assertTrue(t("admin_schedule_command_error", language))

    def test_task_074_parses_schedule_commands(self):
        self.assertEqual(date(2026, 5, 8), parse_set_active_date_command("/set_active_date 2026-05-08"))
        self.assertEqual((time(14, 0), time(19, 0), 10, 1), parse_set_schedule_command("/set_schedule 14:00 19:00 10 1"))
        with self.assertRaisesRegex(AdminScheduleError, "invalid_active_date"):
            parse_set_active_date_command("/set_active_date 08.05.2026")
        with self.assertRaisesRegex(AdminScheduleError, "invalid_schedule"):
            parse_set_schedule_command("/set_schedule 19:00 14:00 10 1")
        with self.assertRaisesRegex(AdminScheduleError, "invalid_schedule"):
            parse_set_schedule_command("/set_schedule 14:00 19:00 0 1")
        with self.assertRaisesRegex(AdminScheduleError, "invalid_schedule"):
            parse_set_schedule_command("/set_schedule 14:00 19:00 10 0")

    async def test_task_074_repository_deletes_settings(self):
        db = FakeConnection()
        repository = SettingsRepository(db)
        await repository.set("active_date", "2026-05-08")
        self.assertEqual("2026-05-08", await repository.get("active_date"))
        await repository.delete("active_date")
        self.assertIsNone(await repository.get("active_date"))
        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("DELETE FROM settings", queries)
        self.assertIn("WHERE key = $1", queries)

    def test_task_074_formats_schedule_reports(self):
        settings = ScheduleSettings(
            active_date=date(2026, 5, 8),
            start_at=time(14, 0),
            end_at=time(19, 0),
            step_minutes=10,
            capacity=1,
        )
        report = format_schedule_settings_report(settings, language="ru")
        active = format_active_date_report(date(2026, 5, 8), language="ru")
        empty = format_active_date_report(None, language="ru")

        self.assertIn("Настройки расписания", report)
        self.assertIn("Активная дата: 2026-05-08", report)
        self.assertIn("Время: 14:00-19:00", report)
        self.assertIn("Шаг: 10", report)
        self.assertIn("Capacity: 1", report)
        self.assertIn("Активная дата: 2026-05-08", active)
        self.assertEqual(t("admin_active_date_not_set", "ru"), empty)

    async def test_task_074_service_manages_active_date_and_schedule_settings(self):
        connection = FakeConnection()
        service = AdminScheduleService(FakePool(connection))

        await service.set_active_date(date(2026, 5, 8))
        active_date = await service.get_active_date()
        await service.set_schedule(start_at=time(14, 0), end_at=time(19, 0), step_minutes=10, capacity=1)
        settings = await service.get_schedule_settings()
        await service.clear_active_date()

        self.assertEqual(date(2026, 5, 8), active_date)
        self.assertEqual(time(14, 0), settings.start_at)
        self.assertEqual(time(19, 0), settings.end_at)
        self.assertEqual(10, settings.step_minutes)
        self.assertEqual(1, settings.capacity)
        self.assertIsNone(await service.get_active_date())
        self.assertIn("acquire_enter", connection.events)
        with self.assertRaisesRegex(AdminScheduleError, "invalid_schedule"):
            await service.set_schedule(start_at=time(19, 0), end_at=time(14, 0), step_minutes=10, capacity=1)

    async def test_task_074_handlers_require_admin_chat_and_answer_reports(self):
        connection = FakeConnection()
        pool = FakePool(connection)
        config = make_config()
        set_active = FakeMessage(text="/set_active_date 2026-05-08")
        show_active = FakeMessage(text="/active_date")
        set_schedule = FakeMessage(text="/set_schedule 14:00 19:00 10 1")
        schedule = FakeMessage(text="/schedule_settings")
        clear_active = FakeMessage(text="/clear_active_date")
        active_menu = FakeMessage(text=t("admin_menu_active_date", "ru"))
        stranger = FakeMessage(chat_id=42, text="/set_active_date 2026-05-08")

        await handle_admin_set_active_date(set_active, db_pool=pool, config=config)
        await handle_admin_show_active_date(show_active, db_pool=pool, config=config)
        await handle_admin_set_schedule(set_schedule, db_pool=pool, config=config)
        await handle_admin_schedule_settings(schedule, db_pool=pool, config=config)
        await handle_admin_clear_active_date(clear_active, db_pool=pool, config=config)
        await handle_admin_active_date_menu(active_menu, db_pool=pool, config=config)
        await handle_admin_set_active_date(stranger, db_pool=pool, config=config)

        self.assertIn("Активная дата установлена: 2026-05-08", set_active.answers[0][0])
        self.assertIn("Активная дата: 2026-05-08", show_active.answers[0][0])
        self.assertIn("Настройки расписания обновлены", set_schedule.answers[0][0])
        self.assertIn("Настройки расписания", schedule.answers[0][0])
        self.assertIn("Активная дата очищена", clear_active.answers[0][0])
        self.assertIn("/set_active_date", active_menu.answers[0][0])
        self.assertEqual(t("admin_only", "ru"), stranger.answers[0][0])


if __name__ == "__main__":
    unittest.main()
