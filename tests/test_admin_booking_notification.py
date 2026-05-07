import unittest
from datetime import date, datetime, time, timezone

from aiogram.types import InlineKeyboardMarkup

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.keyboards.admin import booking_complete_keyboard
from bot.routers.client import handle_booking_confirm
from bot.services.booking_notifications import format_admin_new_booking_message
from bot.services.slots import BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX


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
        self.connection.calls.append(("pool_fetchval", query, args))
        return self.language


class FakeConnection:
    def __init__(self):
        self.events = []
        self.calls = []
        self.locked_slots = []
        self.capacity_counts = []
        self.existing_booking_id = None
        self.fetchval_result = 700
        self.booking_details = None

    def transaction(self):
        self.events.append("transaction_called")
        return FakeTransaction(self)

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "FOR UPDATE" in query:
            return self.locked_slots
        if "GROUP BY bs.slot_id" in query:
            return self.capacity_counts
        return []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "matching_booking" in query or "ARRAY_AGG" in query:
            return self.existing_booking_id
        return self.fetchval_result

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "booking_slots" in query and "string_agg" in query:
            return self.booking_details
        return None

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE 1"


class FakeUser:
    def __init__(self, *, id=42):
        self.id = id


class FakeCallbackMessage:
    def __init__(self):
        self.edited_texts = []

    async def edit_text(self, text, **kwargs):
        self.edited_texts.append((text, kwargs))


class FakeBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append((chat_id, text, kwargs))


class FailingBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append((chat_id, text, kwargs))
        raise RuntimeError("telegram send failed")


class FakeCallback:
    def __init__(self, *, data, from_user=None, message=None, bot=None):
        self.data = data
        self.from_user = from_user or FakeUser()
        self.message = message or FakeCallbackMessage()
        self.bot = bot or FakeBot()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


def make_config(admin_chat_id=-100123):
    return Config(
        **{
            "bot_" + "token": "***",
            "database_url": "postgresql://prananew:***@127.0.0.1:5432/prananew",
            "admin_chat_id": admin_chat_id,
        }
    )


def slot(slot_id, hour, minute, *, capacity=2, blocked=False, duration=10):
    return {
        "id": slot_id,
        "slot_date": date(2026, 5, 8),
        "starts_at": time(hour, minute),
        "start_time": datetime(2026, 5, 8, hour, minute, tzinfo=timezone.utc),
        "duration_minutes": duration,
        "capacity": capacity,
        "is_blocked": blocked,
    }


def booking_details():
    return {
        "booking_id": 700,
        "user_id": 42,
        "username": "alice",
        "first_name": "Alice",
        "last_name": "Tester",
        "slot_date": date(2026, 5, 8),
        "slots_label": "14:00, 14:10",
        "pickup_time": datetime(2026, 5, 8, 14, 10, tzinfo=timezone.utc),
    }


class AdminBookingNotificationTest(unittest.IsolatedAsyncioTestCase):
    def test_task_061_i18n_contains_admin_new_booking_key(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("admin_new_booking", language))

    def test_task_061_admin_new_booking_formatter_contains_required_fields(self):
        text = format_admin_new_booking_message(booking_details(), language="ru")

        self.assertIn("🆕", text)
        self.assertIn(t("admin_new_booking", "ru"), text)
        self.assertIn("#700", text)
        self.assertIn("@alice", text)
        self.assertIn("08.05.2026", text)
        self.assertIn("14:00, 14:10", text)
        self.assertIn("14:10", text)

    def test_task_061_complete_keyboard_is_used_for_admin_notification(self):
        keyboard = booking_complete_keyboard(700, language="ru")

        self.assertIsInstance(keyboard, InlineKeyboardMarkup)
        self.assertEqual("complete_booking:700", keyboard.inline_keyboard[0][0].callback_data)

    async def test_task_061_confirm_callback_notifies_admin_chat_after_successful_booking(self):
        connection = FakeConnection()
        connection.locked_slots = [slot(10, 14, 0), slot(11, 14, 10)]
        connection.booking_details = booking_details()
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX}10,11")

        await handle_booking_confirm(callback, db_pool=FakePool(connection), config=make_config())

        self.assertEqual((None, {}), callback.answers[0])
        self.assertEqual(1, len(callback.bot.sent_messages))
        chat_id, text, kwargs = callback.bot.sent_messages[0]
        self.assertEqual(-100123, chat_id)
        self.assertIn(t("admin_new_booking", "ru"), text)
        self.assertIn("#700", text)
        self.assertIsInstance(kwargs["reply_markup"], InlineKeyboardMarkup)
        self.assertEqual("complete_booking:700", kwargs["reply_markup"].inline_keyboard[0][0].callback_data)
        queries = "\n".join(call[1] for call in connection.calls)
        self.assertIn("FROM bookings", queries)
        self.assertIn("booking_slots", queries)
        self.assertIn("users", queries)
        self.assertIn("s.starts_at", queries)
        self.assertNotIn("to_char(s.start_time", queries)

    async def test_task_061_admin_notification_failure_does_not_break_client_confirmation(self):
        connection = FakeConnection()
        connection.locked_slots = [slot(10, 14, 0)]
        connection.booking_details = booking_details()
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX}10", bot=FailingBot())

        await handle_booking_confirm(callback, db_pool=FakePool(connection), config=make_config())

        self.assertEqual((None, {}), callback.answers[0])
        self.assertEqual(1, len(callback.message.edited_texts))
        client_text, client_kwargs = callback.message.edited_texts[0]
        self.assertIn(t("booking_confirmed", "ru", booking_id=700), client_text)
        self.assertIsInstance(client_kwargs["reply_markup"], InlineKeyboardMarkup)


if __name__ == "__main__":
    unittest.main()
