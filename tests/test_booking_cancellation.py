import unittest
from datetime import datetime, timezone

from aiogram.types import InlineKeyboardMarkup

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.keyboards.client import booking_cancel_keyboard
from bot.routers.client import create_client_router, handle_booking_cancel
from bot.services.bookings import BookingCancellationError, BookingService
from bot.services.slots import BOOKING_CANCEL_CALLBACK_PREFIX


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
        return "EXECUTE 1"

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return None


class FakeUser:
    def __init__(self, *, id=42):
        self.id = id


class FakeCallbackMessage:
    def __init__(self):
        self.edited_texts = []

    async def edit_text(self, text, **kwargs):
        self.edited_texts.append((text, kwargs))


class FakeCallback:
    def __init__(self, *, data, from_user=None, message=None):
        self.data = data
        self.from_user = from_user or FakeUser()
        self.message = message or FakeCallbackMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


def booking(booking_id=700, user_id=42, status="active"):
    return {
        "id": booking_id,
        "user_id": user_id,
        "status": status,
        "pickup_time": datetime(2026, 5, 8, 14, 10, tzinfo=timezone.utc),
    }


class BookingCancellationTest(unittest.IsolatedAsyncioTestCase):
    def test_task_051_i18n_contains_cancellation_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("cancel_booking", language))
            self.assertTrue(t("booking_cancelled", language, booking_id=700))
            self.assertTrue(t("booking_cancel_unavailable", language))

    def test_task_051_cancel_keyboard_uses_inline_callback(self):
        keyboard = booking_cancel_keyboard(700, language="ru")

        self.assertIsInstance(keyboard, InlineKeyboardMarkup)
        self.assertEqual(t("cancel_booking", "ru"), keyboard.inline_keyboard[0][0].text)
        self.assertEqual(f"{BOOKING_CANCEL_CALLBACK_PREFIX}700", keyboard.inline_keyboard[0][0].callback_data)

    async def test_task_051_service_cancels_active_booking_inside_transaction(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "active")
        pool = FakePool(connection)

        cancelled = await BookingService(pool).cancel_booking(user_id=42, booking_id=700)

        self.assertTrue(cancelled)
        self.assertIn("commit", connection.events)
        queries = "\n".join(call[1] for call in connection.calls)
        self.assertIn("FOR UPDATE", queries)
        self.assertIn("UPDATE bookings", queries)
        update_args = [call[2] for call in connection.calls if "UPDATE bookings" in call[1]][0]
        self.assertEqual((700, "cancelled"), update_args[:2])

    async def test_task_051_service_is_idempotent_for_already_cancelled_booking(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "cancelled")
        pool = FakePool(connection)

        cancelled = await BookingService(pool).cancel_booking(user_id=42, booking_id=700)

        self.assertFalse(cancelled)
        self.assertIn("commit", connection.events)
        self.assertFalse(any("UPDATE bookings" in call[1] for call in connection.calls))

    async def test_task_051_service_rolls_back_for_missing_or_foreign_booking(self):
        missing_connection = FakeConnection()
        with self.assertRaisesRegex(BookingCancellationError, "booking_not_found"):
            await BookingService(FakePool(missing_connection)).cancel_booking(user_id=42, booking_id=700)
        self.assertIn("rollback", missing_connection.events)

        foreign_connection = FakeConnection()
        foreign_connection.booking_row = booking(700, 99, "active")
        with self.assertRaisesRegex(BookingCancellationError, "booking_not_found"):
            await BookingService(FakePool(foreign_connection)).cancel_booking(user_id=42, booking_id=700)
        self.assertIn("rollback", foreign_connection.events)

    async def test_task_051_service_rejects_completed_booking(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "completed")
        pool = FakePool(connection)

        with self.assertRaisesRegex(BookingCancellationError, "booking_cannot_cancel"):
            await BookingService(pool).cancel_booking(user_id=42, booking_id=700)

        self.assertIn("rollback", connection.events)
        self.assertFalse(any("UPDATE bookings" in call[1] for call in connection.calls))

    async def test_task_051_cancel_callback_edits_message_on_success(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "active")
        callback = FakeCallback(data=f"{BOOKING_CANCEL_CALLBACK_PREFIX}700")

        await handle_booking_cancel(callback, db_pool=FakePool(connection))

        self.assertEqual((None, {}), callback.answers[0])
        text, kwargs = callback.message.edited_texts[0]
        self.assertIn(t("booking_cancelled", "ru", booking_id=700), text)
        self.assertNotIn("reply_markup", kwargs)

    async def test_task_051_cancel_callback_is_idempotent_for_already_cancelled_booking(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "cancelled")
        callback = FakeCallback(data=f"{BOOKING_CANCEL_CALLBACK_PREFIX}700")

        await handle_booking_cancel(callback, db_pool=FakePool(connection))

        self.assertEqual((None, {}), callback.answers[0])
        text, _ = callback.message.edited_texts[0]
        self.assertIn(t("booking_cancelled", "ru", booking_id=700), text)

    async def test_task_051_cancel_callback_alerts_when_booking_cannot_be_cancelled(self):
        connection = FakeConnection()
        connection.booking_row = booking(700, 42, "completed")
        callback = FakeCallback(data=f"{BOOKING_CANCEL_CALLBACK_PREFIX}700")

        await handle_booking_cancel(callback, db_pool=FakePool(connection))

        self.assertEqual((t("booking_cancel_unavailable", "ru"), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_texts)

    def test_task_051_router_registers_cancel_callback(self):
        router = create_client_router()
        callback_handlers = [handler.callback for handler in router.callback_query.handlers]

        self.assertIn(handle_booking_cancel, callback_handlers)


if __name__ == "__main__":
    unittest.main()
