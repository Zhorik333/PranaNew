import unittest
from datetime import datetime, timezone

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.reviews import ReviewsRepository
from bot.routers.client import handle_public_reviews_more, handle_reviews_menu
from bot.services.reviews import (
    PUBLIC_REVIEWS_MORE_CALLBACK_PREFIX,
    PublicReviewsService,
    build_public_reviews_more_callback_data,
    format_public_reviews_report,
    parse_public_reviews_more_callback_data,
)


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
        self.edits = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup, kwargs))

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.edits.append((text, reply_markup, kwargs))


class FakeCallback:
    def __init__(self, data, user=None, message=None):
        self.data = data
        self.from_user = user or FakeUser()
        self.message = message or FakeMessage(user=self.from_user)
        self.answers = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.answers.append((text, show_alert, kwargs))


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
        limit = int(args[0]) if args else len(self.reviews)
        offset = int(args[1]) if len(args) > 1 else 0
        return self.reviews[offset : offset + limit]

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
        self.assertEqual((7, 0), db.calls[-1][2])

    async def test_task_082_service_lists_published_reviews_with_limit_cap(self):
        db = FakeDatabase()
        service = PublicReviewsService(FakePool(db))

        rows = await service.list_published_reviews(limit=999)

        self.assertEqual(db.reviews, rows)
        self.assertEqual(20, db.calls[-1][2][0])

    async def test_task_083_repository_lists_published_reviews_with_offset(self):
        db = FakeDatabase()
        repo = ReviewsRepository(db)

        await repo.list_published(limit=5, offset=10)

        query = db.calls[-1][1]
        self.assertIn("OFFSET $2", query)
        self.assertEqual((5, 10), db.calls[-1][2])

    async def test_task_083_service_uses_page_size_plus_one_to_detect_more_reviews(self):
        db = FakeDatabase()
        db.reviews = [public_review_row(id=i, text=f"review {i}", username=f"client{i}") for i in range(25)]
        service = PublicReviewsService(FakePool(db))

        page = await service.list_published_page(page=2, page_size=10)

        self.assertEqual(2, page.page)
        self.assertEqual(10, len(page.reviews))
        self.assertTrue(page.has_next)
        self.assertEqual(3, page.next_page)
        self.assertEqual((11, 10), db.calls[-1][2])

    def test_task_083_more_reviews_callback_data_is_strictly_parsed(self):
        self.assertEqual(2, parse_public_reviews_more_callback_data("reviews_more:2"))
        self.assertEqual("reviews_more:3", build_public_reviews_more_callback_data(3))
        with self.assertRaises(ValueError):
            parse_public_reviews_more_callback_data("reviews_more:0")
        with self.assertRaises(ValueError):
            parse_public_reviews_more_callback_data("reviews_more:abc")
        with self.assertRaises(ValueError):
            parse_public_reviews_more_callback_data("other:2")
        for malformed in ("reviews_more:", "reviews_more:+2", "reviews_more: 2", "reviews_more:02", "reviews_more:2:extra"):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    parse_public_reviews_more_callback_data(malformed)

    def test_task_082_formats_public_reviews_with_html_escaping(self):
        text = format_public_reviews_report(
            [public_review_row(rating=5), public_review_row(id=12, username=None, full_name="No <Username>", rating=4)],
            language="ru",
        )

        self.assertIn(t("published_reviews_title", "ru"), text)
        self.assertIn("Очень вкусно &lt;спасибо&gt;", text)
        self.assertIn("@bad&lt;user&gt;", text)
        self.assertIn("No &lt;Username&gt;", text)
        self.assertIn("08.05.2026", text)
        self.assertIn("★★★★★", text)
        self.assertIn("★★★★☆", text)
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

    async def test_task_083_reviews_menu_adds_more_button_when_next_page_exists(self):
        db = FakeDatabase()
        db.reviews = [public_review_row(id=i, text=f"review {i}", username=f"client{i}") for i in range(11)]
        msg = FakeMessage(text=t("menu_reviews", "ru"))

        await handle_reviews_menu(msg, FakePool(db))

        answer_text, reply_markup, kwargs = msg.answers[-1]
        self.assertIn("review 0", answer_text)
        more_button = reply_markup.inline_keyboard[-1][0]
        self.assertEqual(t("public_reviews_more", "ru"), more_button.text)
        self.assertEqual("reviews_more:2", more_button.callback_data)

    async def test_task_083_more_reviews_callback_edits_next_page(self):
        db = FakeDatabase()
        db.reviews = [public_review_row(id=i, text=f"review {i}", username=f"client{i}") for i in range(25)]
        callback = FakeCallback("reviews_more:2")

        await handle_public_reviews_more(callback, FakePool(db))

        self.assertEqual(1, len(callback.message.edits))
        answer_text, reply_markup, kwargs = callback.message.edits[-1]
        self.assertIn("review 10", answer_text)
        self.assertNotIn("review 0", answer_text)
        self.assertEqual("reviews_more:3", reply_markup.inline_keyboard[-1][0].callback_data)
        self.assertEqual((None, False, {}), callback.answers[-1])

    async def test_task_083_invalid_more_reviews_callback_answers_alert(self):
        db = FakeDatabase()
        callback = FakeCallback("reviews_more:oops")

        await handle_public_reviews_more(callback, FakePool(db))

        self.assertEqual(0, len(callback.message.edits))
        self.assertEqual(t("published_reviews_empty", "ru"), callback.answers[-1][0])
        self.assertTrue(callback.answers[-1][1])

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
            self.assertTrue(t("public_reviews_more", language))
