import unittest
from datetime import date, datetime, time, timezone

from bot.i18n import t
from bot.routers.client import handle_booking_confirm, handle_booking_preview, handle_slot_selected
from bot.services.bookings import BookingCreationError, BookingService
from bot.services.slots import BOOKING_PREVIEW_CALLBACK_PREFIX, BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX


class FakeAcquire:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeTransaction:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        self.db.events.append("transaction_enter")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.db.events.append("rollback" if exc_type else "commit")
        return False


class FakeCallbackMessage:
    def __init__(self):
        self.edited_reply_markups = []
        self.edited_texts = []

    async def edit_reply_markup(self, **kwargs):
        self.edited_reply_markups.append(kwargs)

    async def edit_text(self, text, **kwargs):
        self.edited_texts.append((text, kwargs))


class FakeUser:
    def __init__(self, *, id=42):
        self.id = id


class FakeCallback:
    def __init__(self, *, data, message=None):
        self.data = data
        self.from_user = FakeUser()
        self.message = message or FakeCallbackMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class FakeDbPool:
    def __init__(self, *, max_consecutive="2"):
        self.settings = {
            "max_consecutive": max_consecutive,
        }
        self.language = "ru"
        self.fetch_result = []
        self.locked_slots = []
        self.capacity_counts = []
        self.existing_booking_id = None
        self.fetchval_result = 900
        self.calls = []
        self.events = []

    def acquire(self):
        return FakeAcquire(self)

    def transaction(self):
        return FakeTransaction(self)

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "FOR UPDATE" in query:
            return self.locked_slots
        if "GROUP BY bs.slot_id" in query:
            return self.capacity_counts
        return self.fetch_result

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "FROM settings" in query:
            return self.settings.get(args[0])
        if "matching_booking" in query or "ARRAY_AGG" in query:
            return self.existing_booking_id
        if "FROM users" in query:
            return self.language
        return self.fetchval_result

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE 1"

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return None


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


class MaxConsecutiveSettingTest(unittest.IsolatedAsyncioTestCase):
    async def test_task_044_slot_selection_uses_saved_max_consecutive_setting(self):
        db = FakeDbPool(max_consecutive="2")
        db.fetch_result = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]
        callback = FakeCallback(data="slot:12|10,11")

        await handle_slot_selected(callback, db_pool=db)

        self.assertEqual((t("max_consecutive_error", "ru", max_slots=2), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_reply_markups)

    async def test_task_044_preview_validation_uses_saved_max_consecutive_setting(self):
        db = FakeDbPool(max_consecutive="2")
        db.fetch_result = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CALLBACK_PREFIX}10,11,12")

        await handle_booking_preview(callback, db_pool=db)

        self.assertEqual((t("max_consecutive_error", "ru", max_slots=2), {"show_alert": True}), callback.answers[0])
        self.assertEqual([], callback.message.edited_texts)

    async def test_task_044_confirm_validation_uses_saved_max_consecutive_setting(self):
        db = FakeDbPool(max_consecutive="2")
        db.locked_slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]
        callback = FakeCallback(data=f"{BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX}10,11,12")

        await handle_booking_confirm(callback, db_pool=db)

        self.assertEqual((t("max_consecutive_error", "ru", max_slots=2), {"show_alert": True}), callback.answers[0])
        self.assertFalse(any("INSERT INTO bookings" in call[1] for call in db.calls))

    async def test_task_044_booking_service_accepts_explicit_max_consecutive_limit(self):
        db = FakeDbPool(max_consecutive="2")
        db.locked_slots = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        with self.assertRaisesRegex(BookingCreationError, "max_consecutive"):
            await BookingService(db).create_booking(user_id=42, selected_slot_ids=[10, 11, 12], max_consecutive=2)

        self.assertIn("rollback", db.events)
        self.assertFalse(any("INSERT INTO bookings" in call[1] for call in db.calls))


if __name__ == "__main__":
    unittest.main()
