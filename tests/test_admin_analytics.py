import unittest
from datetime import date

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.analytics import AnalyticsRepository
from bot.routers.admin import handle_admin_analytics_report
from bot.routers.client import handle_free_slots_menu
from bot.services.analytics import (
    AnalyticsService,
    format_admin_analytics_report,
    parse_admin_analytics_command,
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

    async def execute(self, query, *args):
        return await self.connection.execute(query, *args)

    async def fetchrow(self, query, *args):
        return await self.connection.fetchrow(query, *args)

    async def fetch(self, query, *args):
        return await self.connection.fetch(query, *args)


class FakeConnection:
    def __init__(self):
        self.events = []
        self.calls = []
        self.fetchrow_result = {
            "slot_date": date(2026, 5, 8),
            "free_slots_views": 7,
            "created_bookings": 5,
            "active_bookings": 2,
            "cancelled_bookings": 1,
            "completed_bookings": 2,
            "total_slots": 10,
            "total_capacity": 12,
            "occupied_slots": 4,
        }
        self.execute_error = None
        self.fetchrow_error = None
        self.available_slots = []

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        if self.execute_error is not None:
            raise self.execute_error
        return "INSERT 0 1"

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if self.fetchrow_error is not None:
            raise self.fetchrow_error
        if "FROM users" in query:
            return {"language": "ru"}
        return self.fetchrow_result

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "FROM slots" in query and "HAVING COUNT" in query:
            return self.available_slots
        return []


class FakeChat:
    def __init__(self, id):
        self.id = id


class FakeUser:
    def __init__(self, id=7001, language_code="ru"):
        self.id = id
        self.language_code = language_code
        self.username = "client"
        self.first_name = "Client"
        self.last_name = "User"


class FakeMessage:
    def __init__(self, *, chat_id=-100123, text="/analytics 2026-05-08", user_id=7001):
        self.chat = FakeChat(chat_id)
        self.from_user = FakeUser(user_id)
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


class AdminAnalyticsTest(unittest.IsolatedAsyncioTestCase):
    def test_task_091_i18n_contains_analytics_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("admin_analytics_help", language))
            self.assertTrue(t("admin_analytics_report_title", language, slot_date="2026-05-08"))
            self.assertTrue(t("admin_analytics_command_error", language))

    def test_task_091_parses_analytics_command(self):
        self.assertEqual(date(2026, 5, 8), parse_admin_analytics_command("/analytics 2026-05-08"))
        with self.assertRaises(ValueError):
            parse_admin_analytics_command("/analytics")
        with self.assertRaises(ValueError):
            parse_admin_analytics_command("/analytics 08.05.2026")

    async def test_task_091_repository_records_free_slot_view_and_builds_report_query(self):
        db = FakeConnection()
        repository = AnalyticsRepository(db)

        await repository.record_free_slots_view(user_id=7001)
        report = await repository.get_daily_report(slot_date=date(2026, 5, 8))

        self.assertEqual(db.fetchrow_result, report)
        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("INSERT INTO analytics_events", queries)
        self.assertIn("free_slots_view", queries)
        self.assertIn("COUNT(*) FILTER", queries)
        self.assertIn("LEFT JOIN booking_slots", queries)
        self.assertIn("occupancy_metrics", queries)
        self.assertIn("COALESCE(SUM(capacity), 0)", queries)
        self.assertNotIn("SUM(s.capacity)", queries)
        self.assertIn("b.status IN ('active', 'completed')", queries)

    async def test_task_091_recording_errors_do_not_break_main_flow(self):
        db = FakeConnection()
        db.execute_error = RuntimeError("temporary analytics write failure")
        service = AnalyticsService(FakePool(db))

        await service.record_free_slots_view(user_id=7001)

        self.assertTrue(any("INSERT INTO analytics_events" in call[1] for call in db.calls))

    async def test_task_091_report_errors_return_controlled_admin_message(self):
        connection = FakeConnection()
        connection.fetchrow_error = RuntimeError("analytics table is unavailable")
        pool = FakePool(connection)
        message = FakeMessage(text="/analytics 2026-05-08")

        await handle_admin_analytics_report(message, db_pool=pool, config=make_config())

        self.assertEqual(t("admin_analytics_command_error", "ru"), message.answers[0][0])

    def test_task_091_formats_daily_report(self):
        row = FakeConnection().fetchrow_result

        report = format_admin_analytics_report(row, language="ru")

        self.assertIn("Аналитика за 2026-05-08", report)
        self.assertIn("Показы свободных слотов: 7", report)
        self.assertIn("Создано броней: 5", report)
        self.assertIn("Отмены: 1", report)
        self.assertIn("Завершения: 2", report)
        self.assertIn("Загрузка слотов: 4/12 (33%)", report)

    async def test_task_091_admin_handler_requires_admin_chat_and_answers_report(self):
        connection = FakeConnection()
        pool = FakePool(connection)
        config = make_config()
        admin_message = FakeMessage(text="/analytics 2026-05-08")
        stranger = FakeMessage(chat_id=42, text="/analytics 2026-05-08")

        await handle_admin_analytics_report(admin_message, db_pool=pool, config=config)
        await handle_admin_analytics_report(stranger, db_pool=pool, config=config)

        self.assertIn("Аналитика за 2026-05-08", admin_message.answers[0][0])
        self.assertEqual(t("admin_only", "ru"), stranger.answers[0][0])

    async def test_task_091_free_slots_menu_records_view_but_still_answers_if_analytics_fails(self):
        connection = FakeConnection()
        connection.execute_error = RuntimeError("analytics down")
        pool = FakePool(connection)
        message = FakeMessage(text=t("menu_free_slots", "ru"))

        await handle_free_slots_menu(message, db_pool=pool)

        self.assertEqual(t("no_slots_available", "ru"), message.answers[0][0])
        self.assertTrue(any("INSERT INTO analytics_events" in call[1] for call in connection.calls))


if __name__ == "__main__":
    unittest.main()
