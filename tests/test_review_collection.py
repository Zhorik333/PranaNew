import unittest
from datetime import datetime, timezone

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.reviews import ReviewsRepository
from bot.routers.client import (
    handle_review_request,
    handle_review_text,
)
from bot.services.bookings import build_review_request_callback_data
from bot.services.reviews import ReviewCollectionError, ReviewService, parse_review_request_callback_data
from bot.states.reviews import ReviewStates


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeAcquire:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, db):
        self.db = db

    def acquire(self):
        return FakeAcquire(self.db)

    async def fetchval(self, query, *args):
        return await self.db.fetchval(query, *args)

    async def fetchrow(self, query, *args):
        return await self.db.fetchrow(query, *args)

    async def fetch(self, query, *args):
        return await self.db.fetch(query, *args)

    async def execute(self, query, *args):
        return await self.db.execute(query, *args)


class FakeDatabase:
    def __init__(self):
        self.calls = []
        self.reviews = []
        self.booking = booking_row()
        self.existing_review = None

    def transaction(self):
        return FakeTransaction()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FROM bookings" in query:
            return self.booking
        if "FROM reviews" in query:
            return self.existing_review
        if "INSERT INTO reviews" in query:
            row = review_row(booking_id=args[0], user_id=args[1], text=args[2], rating=args[3])
            self.reviews.append(row)
            self.existing_review = row
            return row
        return None

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.reviews

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return "ru"

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE 1"


class FakeUser:
    def __init__(self, id=7001):
        self.id = id


class FakeCallback:
    def __init__(self, *, data=None, user_id=7001, message=None):
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = message or FakeMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class FakeMessage:
    def __init__(self, *, user_id=7001, text="Отличная пицца!"):
        self.from_user = FakeUser(user_id)
        self.text = text
        self.answers = []
        self.edits = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeState:
    def __init__(self):
        self.data = {}
        self.state = None
        self.cleared = False

    async def set_state(self, state):
        self.state = state

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_data(self):
        return dict(self.data)

    async def clear(self):
        self.cleared = True
        self.state = None
        self.data.clear()


def booking_row(*, booking_id=51, user_id=7001, status="completed"):
    return {
        "id": booking_id,
        "user_id": user_id,
        "status": status,
    }


def review_row(*, review_id=9, booking_id=51, user_id=7001, text="Отличная пицца!", rating=None, status="pending"):
    return {
        "id": review_id,
        "booking_id": booking_id,
        "user_id": user_id,
        "status": status,
        "text": text,
        "rating": rating,
        "created_at": datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        "moderated_at": None,
    }


class ReviewCollectionTest(unittest.IsolatedAsyncioTestCase):
    def test_task_080_i18n_contains_review_collection_keys(self):
        keys = [
            "review_prompt",
            "review_saved",
            "review_unavailable",
            "review_already_exists",
            "review_empty_error",
        ]
        for language in SUPPORTED_LANGUAGES:
            for key in keys:
                self.assertTrue(t(key, language))

    def test_task_080_parses_review_request_callback_data(self):
        self.assertEqual(51, parse_review_request_callback_data(build_review_request_callback_data(51)))
        with self.assertRaises(ValueError):
            parse_review_request_callback_data("leave_review:0")
        with self.assertRaises(ValueError):
            parse_review_request_callback_data("bad:51")

    async def test_task_080_repository_checks_existing_review_and_booking_owner(self):
        db = FakeDatabase()
        repo = ReviewsRepository(db)

        booking = await repo.get_completed_booking_for_review(booking_id=51, user_id=7001)
        existing = await repo.get_by_booking_id(51)
        created = await repo.create_review(booking_id=51, user_id=7001, text="Great", rating=None)

        self.assertEqual(db.booking, booking)
        self.assertIsNone(existing)
        self.assertEqual("Great", created["text"])
        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("FROM bookings", queries)
        self.assertIn("FOR UPDATE", queries)
        self.assertIn("FROM reviews", queries)
        self.assertIn("INSERT INTO reviews", queries)
        self.assertNotIn("%s", queries)

    async def test_task_080_service_creates_one_pending_review_for_completed_owner_booking(self):
        db = FakeDatabase()
        service = ReviewService(FakePool(db))

        review = await service.submit_review(booking_id=51, user_id=7001, text="  Отлично!  ")

        self.assertEqual("Отлично!", review["text"])
        self.assertEqual("pending", review["status"])
        self.assertEqual(1, len(db.reviews))

    async def test_task_080_service_rejects_empty_duplicate_foreign_or_not_completed_reviews(self):
        db = FakeDatabase()
        service = ReviewService(FakePool(db))
        with self.assertRaisesRegex(ReviewCollectionError, "empty_review"):
            await service.submit_review(booking_id=51, user_id=7001, text="   ")

        db.existing_review = review_row()
        with self.assertRaisesRegex(ReviewCollectionError, "review_already_exists"):
            await service.submit_review(booking_id=51, user_id=7001, text="Again")

        db.existing_review = None
        db.booking = None
        with self.assertRaisesRegex(ReviewCollectionError, "review_unavailable"):
            await service.submit_review(booking_id=51, user_id=7001, text="Text")

        db.booking = booking_row(status="active")
        with self.assertRaisesRegex(ReviewCollectionError, "review_unavailable"):
            await service.submit_review(booking_id=51, user_id=7001, text="Text")

    async def test_task_080_handlers_start_fsm_and_save_review_text(self):
        db = FakeDatabase()
        state = FakeState()
        callback_message = FakeMessage()
        callback = FakeCallback(data=build_review_request_callback_data(51), message=callback_message)

        await handle_review_request(callback, db_pool=FakePool(db), state=state)

        self.assertEqual(ReviewStates.waiting_for_text, state.state)
        self.assertEqual({"booking_id": 51}, state.data)
        self.assertIn(t("review_prompt", "ru"), callback_message.answers[-1][0])
        self.assertEqual((None, {}), callback.answers[-1])

        text_message = FakeMessage(text="Всё вкусно")
        await handle_review_text(text_message, db_pool=FakePool(db), state=state)

        self.assertTrue(state.cleared)
        self.assertEqual(1, len(db.reviews))
        self.assertEqual("Всё вкусно", db.reviews[0]["text"])
        self.assertEqual(t("review_saved", "ru"), text_message.answers[-1][0])

    async def test_task_080_handlers_answer_errors_and_clear_state_when_needed(self):
        db = FakeDatabase()
        db.existing_review = review_row()
        state = FakeState()
        await state.update_data(booking_id=99)
        await state.set_state(ReviewStates.waiting_for_text)
        callback = FakeCallback(data=build_review_request_callback_data(51))

        await handle_review_request(callback, db_pool=FakePool(db), state=state)

        self.assertTrue(state.cleared)
        self.assertIsNone(state.state)
        self.assertEqual(t("review_already_exists", "ru"), callback.answers[-1][0])
        self.assertTrue(callback.answers[-1][1]["show_alert"])

        state = FakeState()
        await state.update_data(booking_id=51)
        message = FakeMessage(text="   ")
        await handle_review_text(message, db_pool=FakePool(FakeDatabase()), state=state)

        self.assertFalse(state.cleared)
        self.assertEqual(t("review_empty_error", "ru"), message.answers[-1][0])


if __name__ == "__main__":
    unittest.main()
