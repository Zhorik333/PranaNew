import inspect
import unittest
from datetime import datetime, timezone

from aiogram.types import InlineKeyboardMarkup

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.keyboards.admin import booking_complete_keyboard
from bot.routers.admin import create_admin_router, handle_booking_complete
from bot.services.bookings import (
    BOOKING_COMPLETE_CALLBACK_PREFIX,
    BookingCompletionError,
    BookingService,
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
        self.language = "ru"

    def acquire(self):
        self.connection.events.append("acquire_called")
        return FakeAcquire(self)

    async def fetchval(self, query, *args):
        self.connection.calls.append(("fetchval", query, args))
        return self.language


class FakeConnection:
    def __init__(self):
        self.events = []
        self.calls = []
        self.booking_row = None
        self.review_request_pending = False
        self.review_request_running = False

    def transaction(self):
        self.events.append("transaction_called")
        return FakeTransaction(self)

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FOR UPDATE" in query:
            return self.booking_row
        return None

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        if "INSERT INTO scheduler_jobs" in query:
            self.review_request_pending = True
            self.review_request_running = False
        if "SET status = 'done'" in query:
            self.review_request_pending = False
            self.review_request_running = False
        if "SET status = 'pending'" in query:
            self.review_request_pending = True
            self.review_request_running = False
        return "EXECUTE 1"

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "UPDATE scheduler_jobs" in query and "RETURNING id" in query:
            if self.review_request_pending:
                self.review_request_pending = False
                self.review_request_running = True
                return 1
            return None
        if "FROM scheduler_jobs" in query:
            return 1 if self.review_request_pending else None
        return None


class FakeChat:
    def __init__(self, id=-100123):
        self.id = id


class FakeCallbackMessage:
    def __init__(self, *, chat_id=-100123):
        self.chat = FakeChat(chat_id)
        self.edited_texts = []

    async def edit_text(self, text, **kwargs):
        self.edited_texts.append((text, kwargs))


class FakeBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append((chat_id, text, kwargs))


class FailingBot:
    async def send_message(self, chat_id, text, **kwargs):
        raise RuntimeError("telegram send failed")


class FakeCallback:
    def __init__(self, *, data, chat_id=-100123, bot=None):
        self.data = data
        self.message = FakeCallbackMessage(chat_id=chat_id)
        self.bot = bot or FakeBot()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


def make_config(admin_chat_id=-100123):
    return Config(
        **{
            "bot_" + "token": "123456:ABCDEF",
            "database_url": "postgresql://prananew:***@127.0.0.1:5432/prananew",
            "admin_chat_id": admin_chat_id,
        }
    )


def booking(booking_id=700, user_id=42, status="active"):
    return {
        "id": booking_id,
        "user_id": user_id,
        "status": status,
        "pickup_time": datetime(2026, 5, 8, 14, 10, tzinfo=timezone.utc),
    }


class BookingCompletionTest(unittest.IsolatedAsyncioTestCase):
    def test_task_052_i18n_contains_completion_and_review_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("complete_booking", language))
            self.assertTrue(t("booking_completed", language, booking_id=700))
            self.assertTrue(t("booking_complete_unavailable", language))
            self.assertTrue(t("review_request", language))

    def test_task_052_complete_keyboard_uses_inline_callback(self):
        keyboard = booking_complete_keyboard(700, language="ru")

        self.assertIsInstance(keyboard, InlineKeyboardMarkup)
        self.assertEqual(t("complete_booking", "ru"), keyboard.inline_keyboard[0][0].text)
        self.assertEqual(f"{BOOKING_COMPLETE_CALLBACK_PREFIX}700", keyboard.inline_keyboard[0][0].callback_data)

    async def test_task_052_service_completes_active_booking_inside_transaction(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "active")
        pool = FakePool(connection)

        result = await BookingService(pool).complete_booking(booking_id=700)

        self.assertEqual(
            {"booking_id": 700, "user_id": 42, "changed": True, "review_request_pending": True},
            result,
        )
        self.assertIn("commit", connection.events)
        queries = "\n".join(call[1] for call in connection.calls)
        self.assertIn("FOR UPDATE", queries)
        self.assertIn("UPDATE bookings", queries)
        self.assertIn("INSERT INTO scheduler_jobs", queries)
        update_args = [call[2] for call in connection.calls if "UPDATE bookings" in call[1]][0]
        self.assertEqual((700, "completed"), update_args[:2])

    async def test_task_052_service_is_idempotent_for_already_completed_booking(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "completed")
        pool = FakePool(connection)

        result = await BookingService(pool).complete_booking(booking_id=700)

        self.assertEqual(
            {"booking_id": 700, "user_id": 42, "changed": False, "review_request_pending": False},
            result,
        )
        self.assertIn("commit", connection.events)
        self.assertFalse(any("UPDATE bookings" in call[1] for call in connection.calls))

    async def test_task_052_service_rolls_back_for_missing_or_cancelled_booking(self):
        missing_connection = FakeConnection()
        with self.assertRaisesRegex(BookingCompletionError, "booking_not_found"):
            await BookingService(FakePool(missing_connection)).complete_booking(booking_id=700)
        self.assertIn("rollback", missing_connection.events)

        cancelled_connection = FakeConnection()
        cancelled_connection.booking_row = booking(700, 42, "cancelled")
        with self.assertRaisesRegex(BookingCompletionError, "booking_cannot_complete"):
            await BookingService(FakePool(cancelled_connection)).complete_booking(booking_id=700)
        self.assertIn("rollback", cancelled_connection.events)
        self.assertFalse(any("UPDATE bookings" in call[1] for call in cancelled_connection.calls))

    async def test_task_052_admin_callback_completes_booking_and_requests_review(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "active")
        callback = FakeCallback(data=f"{BOOKING_COMPLETE_CALLBACK_PREFIX}700")

        await handle_booking_complete(callback, db_pool=FakePool(connection), config=make_config())

        self.assertEqual((None, {}), callback.answers[0])
        admin_text, admin_kwargs = callback.message.edited_texts[0]
        self.assertIn(t("booking_completed", "ru", booking_id=700), admin_text)
        self.assertNotIn("reply_markup", admin_kwargs)
        self.assertEqual(1, len(callback.bot.sent_messages))
        chat_id, user_text, user_kwargs = callback.bot.sent_messages[0]
        self.assertEqual(42, chat_id)
        self.assertEqual(t("review_request", "ru"), user_text)
        self.assertIsInstance(user_kwargs["reply_markup"], InlineKeyboardMarkup)

    async def test_task_052_admin_callback_does_not_repeat_review_request_when_already_completed(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "completed")
        callback = FakeCallback(data=f"{BOOKING_COMPLETE_CALLBACK_PREFIX}700")

        await handle_booking_complete(callback, db_pool=FakePool(connection), config=make_config())

        self.assertEqual((t("booking_completed", "ru", booking_id=700), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_texts)
        self.assertEqual([], callback.bot.sent_messages)
        self.assertFalse(any("UPDATE bookings" in call[1] for call in connection.calls))

    async def test_task_052_failed_review_send_keeps_pending_job_for_retry(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "active")
        callback = FakeCallback(data=f"{BOOKING_COMPLETE_CALLBACK_PREFIX}700", bot=FailingBot())

        await handle_booking_complete(callback, db_pool=FakePool(connection), config=make_config())

        self.assertTrue(connection.review_request_pending)
        self.assertFalse(connection.review_request_running)
        self.assertEqual((t("booking_complete_unavailable", "ru"), {"show_alert": True}), callback.answers[0])
        self.assertTrue(any("SET status = 'pending'" in call[1] for call in connection.calls))

    async def test_task_052_admin_callback_retries_pending_review_request_for_completed_booking(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "completed")
        connection.review_request_pending = True
        callback = FakeCallback(data=f"{BOOKING_COMPLETE_CALLBACK_PREFIX}700")

        await handle_booking_complete(callback, db_pool=FakePool(connection), config=make_config())

        self.assertEqual((t("booking_completed", "ru", booking_id=700), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_texts)
        self.assertEqual(1, len(callback.bot.sent_messages))
        self.assertFalse(connection.review_request_pending)
        self.assertTrue(any("UPDATE scheduler_jobs" in call[1] for call in connection.calls))

    async def test_task_052_admin_callback_rejects_non_admin_chat(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "active")
        callback = FakeCallback(data=f"{BOOKING_COMPLETE_CALLBACK_PREFIX}700", chat_id=-999)

        await handle_booking_complete(callback, db_pool=FakePool(connection), config=make_config(admin_chat_id=-100123))

        self.assertEqual((t("admin_only", "ru"), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_texts)
        self.assertFalse(any("UPDATE bookings" in call[1] for call in connection.calls))

    async def test_task_052_admin_callback_alerts_when_booking_cannot_be_completed(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "cancelled")
        callback = FakeCallback(data=f"{BOOKING_COMPLETE_CALLBACK_PREFIX}700")

        await handle_booking_complete(callback, db_pool=FakePool(connection), config=make_config())

        self.assertEqual((t("booking_complete_unavailable", "ru"), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_texts)
        self.assertEqual([], callback.bot.sent_messages)

    def test_task_052_admin_router_registers_complete_callback_without_start_command(self):
        router = create_admin_router()
        callback_handlers = [handler.callback for handler in router.callback_query.handlers]
        source = inspect.getsource(create_admin_router)

        self.assertIn(handle_booking_complete, callback_handlers)
        self.assertNotIn("CommandStart", source)
        self.assertNotIn('Command("start")', source)
        self.assertNotIn("Command('start')", source)


if __name__ == "__main__":
    unittest.main()
