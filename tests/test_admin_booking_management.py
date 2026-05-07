import unittest
from datetime import date, datetime, time, timezone

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.bookings import BookingsRepository
from bot.routers.admin import (
    handle_admin_booking_detail,
    handle_admin_booking_list,
    handle_admin_booking_status,
)
from bot.services.admin_bookings import (
    AdminBookingError,
    AdminBookingsService,
    format_admin_booking_details,
    format_admin_bookings_report,
    parse_admin_booking_detail_command,
    parse_admin_booking_status_command,
    parse_admin_bookings_command,
)


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        self.connection.events.append("transaction_enter")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.connection.events.append("rollback" if exc_type else "commit")
        return False


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
        self.booking_row = None
        self.review_request_pending = False

    def transaction(self):
        self.events.append("transaction_called")
        return FakeTransaction(self)

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.fetch_result

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FOR UPDATE" in query:
            return self.booking_row
        return self.fetchrow_result

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "FROM scheduler_jobs" in query:
            return 1 if self.review_request_pending else None
        return None

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        if "INSERT INTO scheduler_jobs" in query:
            self.review_request_pending = True
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


def booking_row(booking_id=10, user_id=7001, status="active"):
    return {
        "id": booking_id,
        "booking_id": booking_id,
        "user_id": user_id,
        "status": status,
        "username": "masha",
        "first_name": "Masha",
        "last_name": "Ivanova",
        "slot_date": date(2026, 5, 8),
        "slots_label": "14:00, 14:10",
        "pickup_time": datetime(2026, 5, 8, 14, 10, tzinfo=timezone.utc),
        "created_at": datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
        "customer_name": None,
        "customer_phone": None,
        "comment": "",
    }


class AdminBookingManagementTest(unittest.IsolatedAsyncioTestCase):
    def test_task_072_i18n_contains_admin_booking_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("admin_bookings_help", language))
            self.assertTrue(t("admin_bookings_report_title", language, slot_date="2026-05-08", status="active"))
            self.assertTrue(t("admin_bookings_report_empty", language, slot_date="2026-05-08", status="active"))
            self.assertTrue(t("admin_booking_details_title", language, booking_id=10))
            self.assertTrue(t("admin_booking_status_updated", language, booking_id=10, status="completed"))
            self.assertTrue(t("admin_booking_command_error", language))
            self.assertTrue(t("admin_booking_status_active", language))
            self.assertTrue(t("admin_booking_status_cancelled", language))

    def test_task_072_parses_admin_booking_commands(self):
        self.assertEqual((date(2026, 5, 8), None), parse_admin_bookings_command("/bookings 2026-05-08"))
        self.assertEqual((date(2026, 5, 8), "active"), parse_admin_bookings_command("/bookings 2026-05-08 active"))
        self.assertEqual((date(2026, 5, 8), "completed"), parse_admin_bookings_command("/bookings 2026-05-08 completed"))
        self.assertEqual(10, parse_admin_booking_detail_command("/booking 10"))
        self.assertEqual((10, "cancelled"), parse_admin_booking_status_command("/booking_status 10 cancelled"))
        with self.assertRaisesRegex(AdminBookingError, "invalid_status"):
            parse_admin_booking_status_command("/booking_status 10 active")
        with self.assertRaisesRegex(AdminBookingError, "invalid_status"):
            parse_admin_bookings_command("/bookings 2026-05-08 unknown")

    async def test_task_072_repository_lists_by_date_status_and_details(self):
        db = FakeConnection()
        db.fetch_result = [booking_row()]
        db.fetchrow_result = booking_row()
        repository = BookingsRepository(db)

        rows = await repository.list_admin_bookings(slot_date=date(2026, 5, 8), status="active")
        details = await repository.get_admin_booking_details(10)

        self.assertEqual(db.fetch_result, rows)
        self.assertEqual(db.fetchrow_result, details)
        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("JOIN booking_slots", queries)
        self.assertIn("JOIN slots", queries)
        self.assertIn("JOIN users", queries)
        self.assertIn("s.slot_date = $1", queries)
        self.assertIn("($2::text IS NULL OR b.status = $2)", queries)
        self.assertIn("string_agg(to_char(s.starts_at, 'HH24:MI')", queries)

    def test_task_072_formats_booking_list_and_details(self):
        rows = [booking_row(10, status="active"), booking_row(11, status="completed")]

        report = format_admin_bookings_report(date(2026, 5, 8), rows, status=None, language="ru")
        details = format_admin_booking_details(booking_row(10), language="ru")

        self.assertIn("Брони на 2026-05-08", report)
        self.assertIn("#10 14:00, 14:10 @masha active", report)
        self.assertIn("#11 14:00, 14:10 @masha completed ✅", report)
        self.assertIn("Бронь #10", details)
        self.assertIn("Клиент: @masha", details)
        self.assertIn("Слоты: 14:00, 14:10", details)

    def test_task_072_escapes_user_controlled_fields_for_html_parse_mode(self):
        row = booking_row()
        row.update(
            {
                "username": None,
                "first_name": '<a href="tg://user?id=1">admin</a>',
                "last_name": "<b>root</b>",
                "customer_phone": "+382 <script>",
                "comment": "Bring <b>pizza</b> & drinks",
            }
        )

        report = format_admin_bookings_report(date(2026, 5, 8), [row], status="active", language="ru")
        details = format_admin_booking_details(row, language="ru")

        self.assertNotIn('<a href="tg://user?id=1">admin</a>', report)
        self.assertIn('&lt;a href="tg://user?id=1"&gt;admin&lt;/a&gt;', report)
        self.assertIn("&lt;b&gt;root&lt;/b&gt;", details)
        self.assertIn("Телефон: +382 &lt;script&gt;", details)
        self.assertIn("Комментарий: Bring &lt;b&gt;pizza&lt;/b&gt; &amp; drinks", details)

    async def test_task_072_service_lists_details_and_cancels_active_booking(self):
        connection = FakeConnection()
        connection.fetch_result = [booking_row()]
        connection.fetchrow_result = booking_row()
        connection.booking_row = booking_row(status="active")
        service = AdminBookingsService(FakePool(connection))

        rows = await service.list_bookings(slot_date=date(2026, 5, 8), status="active")
        details = await service.get_booking_details(10)
        result = await service.set_booking_status(booking_id=10, status="cancelled")

        self.assertEqual(connection.fetch_result, rows)
        self.assertEqual(connection.fetchrow_result, details)
        self.assertEqual({"booking_id": 10, "status": "cancelled", "changed": True, "review_request_pending": False}, result)
        self.assertIn("commit", connection.events)
        update_args = [call[2] for call in connection.calls if "UPDATE bookings" in call[1]][0]
        self.assertEqual((10, "cancelled"), update_args[:2])

    async def test_task_072_service_completes_active_booking_and_rejects_invalid_transitions(self):
        complete_connection = FakeConnection()
        complete_connection.booking_row = booking_row(status="active")
        result = await AdminBookingsService(FakePool(complete_connection)).set_booking_status(booking_id=10, status="completed")
        self.assertEqual({"booking_id": 10, "status": "completed", "changed": True, "review_request_pending": True}, result)
        self.assertTrue(any("INSERT INTO scheduler_jobs" in call[1] for call in complete_connection.calls))

        cancelled_connection = FakeConnection()
        cancelled_connection.booking_row = booking_row(status="cancelled")
        with self.assertRaisesRegex(AdminBookingError, "invalid_status_transition"):
            await AdminBookingsService(FakePool(cancelled_connection)).set_booking_status(booking_id=10, status="completed")
        self.assertIn("rollback", cancelled_connection.events)

        active_connection = FakeConnection()
        active_connection.booking_row = booking_row(status="active")
        with self.assertRaisesRegex(AdminBookingError, "invalid_status"):
            await AdminBookingsService(FakePool(active_connection)).set_booking_status(booking_id=10, status="active")

    async def test_task_072_handlers_require_admin_chat_and_answer_reports(self):
        connection = FakeConnection()
        connection.fetch_result = [booking_row()]
        connection.fetchrow_result = booking_row()
        connection.booking_row = booking_row(status="active")
        pool = FakePool(connection)
        config = make_config()
        list_message = FakeMessage(text="/bookings 2026-05-08 active")
        details_message = FakeMessage(text="/booking 10")
        status_message = FakeMessage(text="/booking_status 10 cancelled")
        stranger = FakeMessage(chat_id=42, text="/bookings 2026-05-08")

        await handle_admin_booking_list(list_message, db_pool=pool, config=config)
        await handle_admin_booking_detail(details_message, db_pool=pool, config=config)
        await handle_admin_booking_status(status_message, db_pool=pool, config=config)
        await handle_admin_booking_list(stranger, db_pool=pool, config=config)

        self.assertIn("#10", list_message.answers[0][0])
        self.assertIn("Бронь #10", details_message.answers[0][0])
        self.assertEqual(t("admin_booking_status_updated", "ru", booking_id=10, status="cancelled"), status_message.answers[0][0])
        self.assertEqual(t("admin_only", "ru"), stranger.answers[0][0])


if __name__ == "__main__":
    unittest.main()
