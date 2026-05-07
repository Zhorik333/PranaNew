import unittest
from datetime import date, datetime, time, timezone

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.routers.client import create_client_router, handle_booking_confirm, handle_booking_preview
from bot.services.bookings import BookingCreationError, BookingService
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
        self.connection.calls.append(("fetchval", query, args))
        return self.language


class FakeConnection:
    def __init__(self):
        self.events = []
        self.calls = []
        self.locked_slots = []
        self.capacity_counts = []
        self.existing_booking_id = None
        self.fetchval_result = 700

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

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE 1"

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
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


class BookingConfirmationTest(unittest.IsolatedAsyncioTestCase):
    def test_task_050_i18n_contains_booking_confirmation_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("booking_confirmed", language, booking_id=77))
            self.assertTrue(t("booking_unavailable", language))
            self.assertTrue(t("booking_already_confirmed", language, booking_id=77))

    async def test_task_050_service_creates_booking_inside_transaction_after_locking_slots(self):
        connection = FakeConnection()
        connection.locked_slots = [slot(10, 14, 0), slot(11, 14, 10)]
        connection.capacity_counts = [{"slot_id": 10, "booked_count": 0}, {"slot_id": 11, "booked_count": 1}]
        pool = FakePool(connection)

        booking_id = await BookingService(pool).create_booking(user_id=42, selected_slot_ids=[10, 11])

        self.assertEqual(700, booking_id)
        self.assertIn("commit", connection.events)
        self.assertLess(connection.events.index("transaction_enter"), connection.events.index("commit"))
        queries = "\n".join(call[1] for call in connection.calls)
        self.assertIn("FOR UPDATE", queries)
        self.assertIn("INSERT INTO bookings", queries)
        self.assertIn("status", queries)
        self.assertIn("INSERT INTO booking_slots", queries)
        insert_args = [call[2] for call in connection.calls if "INSERT INTO bookings" in call[1]][0]
        self.assertEqual(42, insert_args[0])
        self.assertEqual("active", insert_args[1])
        self.assertEqual([10, 11], [call[2][1] for call in connection.calls if "INSERT INTO booking_slots" in call[1]])

    async def test_task_050_service_rolls_back_when_selected_slot_is_missing(self):
        connection = FakeConnection()
        connection.locked_slots = [slot(10, 14, 0)]
        pool = FakePool(connection)

        with self.assertRaisesRegex(BookingCreationError, "slot_unavailable"):
            await BookingService(pool).create_booking(user_id=42, selected_slot_ids=[10, 11])

        self.assertIn("rollback", connection.events)
        self.assertFalse(any("INSERT INTO bookings" in call[1] for call in connection.calls))

    async def test_task_050_service_rolls_back_when_slot_is_blocked_or_full(self):
        blocked_connection = FakeConnection()
        blocked_connection.locked_slots = [slot(10, 14, 0, blocked=True)]
        with self.assertRaisesRegex(BookingCreationError, "slot_unavailable"):
            await BookingService(FakePool(blocked_connection)).create_booking(user_id=42, selected_slot_ids=[10])
        self.assertIn("rollback", blocked_connection.events)

        full_connection = FakeConnection()
        full_connection.locked_slots = [slot(10, 14, 0, capacity=1)]
        full_connection.capacity_counts = [{"slot_id": 10, "booked_count": 1}]
        with self.assertRaisesRegex(BookingCreationError, "slot_full"):
            await BookingService(FakePool(full_connection)).create_booking(user_id=42, selected_slot_ids=[10])
        self.assertIn("rollback", full_connection.events)

    async def test_task_050_double_click_returns_existing_booking_without_second_insert(self):
        connection = FakeConnection()
        connection.locked_slots = [slot(10, 14, 0), slot(11, 14, 10)]
        connection.existing_booking_id = 77
        pool = FakePool(connection)

        booking_id = await BookingService(pool).create_booking(user_id=42, selected_slot_ids=[10, 11])

        self.assertEqual(77, booking_id)
        self.assertIn("commit", connection.events)
        self.assertFalse(any("INSERT INTO bookings" in call[1] for call in connection.calls))

    async def test_task_050_confirm_callback_creates_booking_and_edits_message(self):
        connection = FakeConnection()
        connection.locked_slots = [slot(10, 14, 0), slot(11, 14, 10)]
        pool = FakePool(connection)
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX}10,11")

        await handle_booking_confirm(callback, db_pool=pool)

        self.assertEqual((None, {}), callback.answers[0])
        text, kwargs = callback.message.edited_texts[0]
        self.assertIn(t("booking_confirmed", "ru", booking_id=700), text)
        self.assertNotIn("reply_markup", kwargs)

    async def test_task_050_confirm_callback_alerts_when_slots_became_unavailable(self):
        connection = FakeConnection()
        connection.locked_slots = [slot(10, 14, 0)]
        pool = FakePool(connection)
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX}10,11")

        await handle_booking_confirm(callback, db_pool=pool)

        self.assertEqual((t("booking_unavailable", "ru"), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_texts)

    def test_task_050_router_registers_confirm_callback_before_other_preview_handlers(self):
        router = create_client_router()
        callback_handlers = [handler.callback for handler in router.callback_query.handlers]

        self.assertIn(handle_booking_confirm, callback_handlers)
        self.assertLess(callback_handlers.index(handle_booking_confirm), callback_handlers.index(handle_booking_preview))


if __name__ == "__main__":
    unittest.main()
