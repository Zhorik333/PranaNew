import unittest
from datetime import date, datetime, timezone

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.users import UsersRepository
from bot.routers.admin import (
    handle_admin_user_detail,
    handle_admin_user_history,
    handle_admin_users_list,
)
from bot.services.admin_users import (
    AdminUserError,
    AdminUsersService,
    format_admin_user_details,
    format_admin_user_history,
    format_admin_users_report,
    parse_admin_user_command,
    parse_admin_user_history_command,
    parse_admin_users_command,
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
        self.fetch_result = []
        self.fetchrow_result = None

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "JOIN booking_slots" in query:
            return [booking_history_row()]
        return self.fetch_result

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_result

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return None

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE 1"


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


def user_row(tg_id=7001, username="masha", first_name="Masha", last_name="Ivanova"):
    return {
        "tg_id": tg_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "language": "ru",
        "created_at": datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 7, 12, 5, tzinfo=timezone.utc),
        "bookings_count": 3,
        "active_bookings_count": 1,
        "completed_bookings_count": 1,
        "cancelled_bookings_count": 1,
        "last_booking_at": datetime(2026, 5, 8, 14, 0, tzinfo=timezone.utc),
    }


def booking_history_row(booking_id=10, status="active"):
    return {
        "booking_id": booking_id,
        "status": status,
        "slot_date": date(2026, 5, 8),
        "slots_label": "14:00, 14:10",
        "pickup_time": datetime(2026, 5, 8, 14, 10, tzinfo=timezone.utc),
        "created_at": datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
        "comment": "",
    }


class AdminUsersHistoryTest(unittest.IsolatedAsyncioTestCase):
    def test_task_073_i18n_contains_admin_user_history_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("admin_users_help", language))
            self.assertTrue(t("admin_users_report_title", language))
            self.assertTrue(t("admin_users_report_empty", language))
            self.assertTrue(t("admin_user_details_title", language, user_id=7001))
            self.assertTrue(t("admin_user_history_title", language, user_id=7001))
            self.assertTrue(t("admin_user_history_empty", language, user_id=7001))
            self.assertTrue(t("admin_user_command_error", language))

    def test_task_073_parses_admin_user_commands(self):
        self.assertEqual((None, 20), parse_admin_users_command("/users"))
        self.assertEqual(("masha", 20), parse_admin_users_command("/users masha"))
        self.assertEqual(("masha", 5), parse_admin_users_command("/users masha 5"))
        self.assertEqual(7001, parse_admin_user_command("/user 7001"))
        self.assertEqual((7001, 10), parse_admin_user_history_command("/user_history 7001"))
        self.assertEqual((7001, 3), parse_admin_user_history_command("/user_history 7001 3"))
        with self.assertRaisesRegex(AdminUserError, "invalid_limit"):
            parse_admin_users_command("/users masha 0")
        with self.assertRaisesRegex(AdminUserError, "invalid_user_id"):
            parse_admin_user_command("/user -1")

    async def test_task_073_repository_lists_users_with_booking_stats_and_history(self):
        db = FakeConnection()
        db.fetch_result = [user_row()]
        db.fetchrow_result = user_row()
        repository = UsersRepository(db)

        users = await repository.list_admin_users(search="masha", limit=20)
        details = await repository.get_admin_user_details(7001)
        history = await repository.list_admin_user_booking_history(user_id=7001, limit=10)

        self.assertEqual(db.fetch_result, users)
        self.assertEqual(db.fetchrow_result, details)
        self.assertEqual([booking_history_row()], history)
        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("LEFT JOIN bookings", queries)
        self.assertIn("COUNT(b.id) AS bookings_count", queries)
        self.assertIn("FILTER (WHERE b.status = 'active')", queries)
        self.assertIn("WHERE u.tg_id = $1", queries)
        self.assertIn("JOIN booking_slots", queries)
        self.assertIn("string_agg(to_char(s.starts_at, 'HH24:MI')", queries)

    def test_task_073_formats_users_details_and_history_with_html_escaping(self):
        malicious = user_row(username=None, first_name='<a href="tg://user?id=1">Admin</a>', last_name="<b>Root</b>")
        users_report = format_admin_users_report([malicious], search=None, language="ru")
        details = format_admin_user_details(malicious, language="ru")
        history = format_admin_user_history(7001, [booking_history_row(10, "completed")], language="ru")

        self.assertIn("Пользователи:", users_report)
        self.assertIn("tg:7001", users_report)
        self.assertIn("броней:3", users_report)
        self.assertNotIn('<a href="tg://user?id=1">Admin</a>', details)
        self.assertIn('&lt;a href="tg://user?id=1"&gt;Admin&lt;/a&gt;', details)
        self.assertIn("&lt;b&gt;Root&lt;/b&gt;", details)
        self.assertIn("История пользователя 7001", history)
        self.assertIn("#10 2026-05-08 14:00, 14:10 completed ✅", history)

    async def test_task_073_service_lists_users_details_and_history(self):
        connection = FakeConnection()
        connection.fetch_result = [user_row()]
        connection.fetchrow_result = user_row()
        service = AdminUsersService(FakePool(connection))

        users = await service.list_users(search="masha", limit=20)
        details = await service.get_user_details(7001)
        history = await service.list_user_history(user_id=7001, limit=10)

        self.assertEqual([user_row()], users)
        self.assertEqual(user_row(), details)
        self.assertEqual([booking_history_row()], history)
        self.assertIn("acquire_enter", connection.events)
        with self.assertRaisesRegex(AdminUserError, "invalid_limit"):
            await service.list_users(search=None, limit=0)
        with self.assertRaisesRegex(AdminUserError, "user_not_found"):
            await AdminUsersService(FakePool(FakeConnection())).get_user_details(7001)

    async def test_task_073_handlers_require_admin_chat_and_answer_reports(self):
        connection = FakeConnection()
        connection.fetch_result = [user_row()]
        connection.fetchrow_result = user_row()
        pool = FakePool(connection)
        config = make_config()
        users_message = FakeMessage(text="/users masha")
        user_message = FakeMessage(text="/user 7001")
        history_message = FakeMessage(text="/user_history 7001")
        stranger = FakeMessage(chat_id=42, text="/users")

        await handle_admin_users_list(users_message, db_pool=pool, config=config)
        await handle_admin_user_detail(user_message, db_pool=pool, config=config)
        await handle_admin_user_history(history_message, db_pool=pool, config=config)
        await handle_admin_users_list(stranger, db_pool=pool, config=config)

        self.assertIn("Пользователи:", users_message.answers[0][0])
        self.assertIn("Пользователь 7001", user_message.answers[0][0])
        self.assertIn("История пользователя 7001", history_message.answers[0][0])
        self.assertEqual(t("admin_only", "ru"), stranger.answers[0][0])


if __name__ == "__main__":
    unittest.main()
