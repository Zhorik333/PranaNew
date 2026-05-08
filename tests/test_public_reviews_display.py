import unittest
from datetime import datetime, timezone

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.reviews import ReviewsRepository
from bot.routers.client import handle_reviews_menu
from bot.services.reviews import PublicReviewsService, format_public_reviews_report


class FakeUser:
    def __init__(self, user_id=7001, language_code="ru"):
        self.id = user_id
        self.username = "client"
        self.first_name = "Client"
        self.last_name = None
        self.language_code = language_code


class FakeMessage:
    def __init__(self, text="Отзывы", user=None):
        self.text = text
        self.from_user = user or FakeUser()
        self.answers = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup, kwargs))


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

    async def fetch(self, query, *args):
        return await self.db.fetch(query, *args)

    async def fetchrow(self, query, *args):
        return await self.db.fetchrow(query, *args)

    async def fetchval(self, query, *args):
        return await self.db.fetchval(query, *args)

    async def execute(self, query, *args):
        return await self.db.execute(query, *args)


class FakeDatabase:
    def __init__(self):
        self.calls = []
        self.language = "ru"
        self.reviews = [public_review_row()]

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.reviews

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FROM users" in query:
            return {"language": self.language}
        return None

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "SELECT language" in query:
            return self.language
        return None

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "OK"


def public_review_row(**overrides):
    row = {
        "id": 11,
        "booking_id": 51,
        "user_id": 7001,
        "status": "published",
        "text": "Очень вкусно <спасибо>",
        "rating": None,
        "created_at": datetime(2026, 5, 8, 14, 30, tzinfo=timezone.utc),
        "moderated_at": datetime(2026, 5, 8, 15, 0, tzinfo=timezone.utc),
        "username": "bad<user>",
        "full_name": "Ann & Bob",
    }
    row.update(overrides)
    return row


class PublicReviewsDisplayTest(unittest.IsolatedAsyncioTestCase):
    async def test_task_082_repository_lists_published_reviews_with_user_labels(self):
        db = FakeDatabase()
        repo = ReviewsRepository(db)

        rows = await repo.list_published(limit=7)

        self.assertEqual(db.reviews, rows)
        query = db.calls[-1][1]
        self.assertIn("WHERE r.status = 'published'", query)
        self.assertIn("LEFT JOIN users", query)
        self.assertIn("concat_ws", query)
        self.assertIn("ORDER BY r.created_at DESC", query)
        self.assertEqual((7,), db.calls[-1][2])

    async def test_task_082_service_lists_published_reviews_with_limit_cap(self):
        db = FakeDatabase()
        service = PublicReviewsService(FakePool(db))

        rows = await service.list_published_reviews(limit=999)

        self.assertEqual(db.reviews, rows)
        self.assertEqual(20, db.calls[-1][2][0])

    def test_task_082_formats_public_reviews_with_html_escaping(self):
        text = format_public_reviews_report(
            [public_review_row(), public_review_row(id=12, username=None, full_name="No <Username>")],
            language="ru",
        )

        self.assertIn(t("published_reviews_title", "ru"), text)
        self.assertIn("Очень вкусно &lt;спасибо&gt;", text)
        self.assertIn("@bad&lt;user&gt;", text)
        self.assertIn("No &lt;Username&gt;", text)
        self.assertIn("08.05.2026", text)
        self.assertNotIn("<спасибо>", text)
        self.assertNotIn("bad<user>", text)

    def test_task_082_formats_empty_public_reviews(self):
        self.assertEqual(t("published_reviews_empty", "ru"), format_public_reviews_report([], language="ru"))

    def test_task_082_formats_public_reviews_with_telegram_safe_length(self):
        rows = [public_review_row(id=i, text="x" * 1000, username=f"client{i}") for i in range(40)]

        text = format_public_reviews_report(rows, language="ru")

        self.assertLessEqual(len(text), 3900)
        self.assertIn("…", text)
        self.assertNotIn("x" * 1000, text)

    def test_task_082_formats_public_reviews_with_telegram_safe_length_for_long_author(self):
        text = format_public_reviews_report(
            [public_review_row(text="ok", username="u" * 5000, full_name=None)],
            language="ru",
        )

        self.assertLessEqual(len(text), 3900)
        self.assertIn("…", text)
        self.assertNotIn("u" * 5000, text)
        self.assertIn("ok", text)

    async def test_task_082_reviews_menu_shows_published_reviews(self):
        db = FakeDatabase()
        msg = FakeMessage(text=t("menu_reviews", "ru"))

        await handle_reviews_menu(msg, FakePool(db))

        self.assertEqual(1, len(msg.answers))
        answer_text, reply_markup, kwargs = msg.answers[-1]
        self.assertIn(t("published_reviews_title", "ru"), answer_text)
        self.assertIn("Очень вкусно &lt;спасибо&gt;", answer_text)
        self.assertIsNotNone(reply_markup)

    async def test_task_082_reviews_menu_shows_empty_message(self):
        db = FakeDatabase()
        db.reviews = []
        msg = FakeMessage(text=t("menu_reviews", "ru"))

        await handle_reviews_menu(msg, FakePool(db))

        self.assertEqual(t("published_reviews_empty", "ru"), msg.answers[-1][0])

    def test_task_082_i18n_contains_public_review_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("published_reviews_title", language))
            self.assertTrue(t("published_reviews_empty", language))
