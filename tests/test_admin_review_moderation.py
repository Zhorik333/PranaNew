import unittest
from datetime import datetime, timezone

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.reviews import ReviewsRepository
from bot.routers.admin import (
    handle_admin_review_detail,
    handle_admin_review_list,
    handle_admin_review_status,
    handle_admin_reviews_menu,
)
from bot.services.admin_reviews import (
    AdminReviewError,
    AdminReviewsService,
    format_admin_review_details,
    format_admin_reviews_report,
    parse_admin_review_command,
    parse_admin_review_status_command,
    parse_admin_reviews_command,
)


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

    async def fetch(self, query, *args):
        return await self.db.fetch(query, *args)

    async def fetchrow(self, query, *args):
        return await self.db.fetchrow(query, *args)

    async def execute(self, query, *args):
        return await self.db.execute(query, *args)


class FakeDatabase:
    def __init__(self):
        self.calls = []
        self.reviews = [review_row()]
        self.detail = review_row(text="<b>Очень вкусно</b>", username="bad<user>", full_name="Ann & Bob")

    def transaction(self):
        return FakeTransaction()

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.reviews

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FOR UPDATE" in query:
            review_id = args[0]
            status = args[1] if len(args) > 1 else None
            if self.detail and self.detail["id"] == review_id and (status is None or self.detail["status"] == status):
                return self.detail
            return None
        if "UPDATE reviews" in query:
            review_id, status = args
            if not self.detail or self.detail["id"] != review_id:
                return None
            self.detail = {**self.detail, "status": status, "moderated_at": datetime(2026, 5, 8, 13, 0, tzinfo=timezone.utc)}
            return self.detail
        return self.detail

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE 1"


class FakeChat:
    def __init__(self, id=9001):
        self.id = id


class FakeMessage:
    def __init__(self, text, *, chat_id=9001):
        self.text = text
        self.chat = FakeChat(chat_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


def config(admin_chat_id=9001):
    return Config(
        bot_token="fake",
        database_url="postgresql://fake/fake",
        admin_chat_id=admin_chat_id,
    )


def review_row(
    *,
    review_id=7,
    booking_id=51,
    user_id=7001,
    status="pending",
    text="Очень вкусно!",
    rating=None,
    username="client",
    full_name="Client Name",
):
    return {
        "id": review_id,
        "booking_id": booking_id,
        "user_id": user_id,
        "status": status,
        "text": text,
        "rating": rating,
        "created_at": datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        "moderated_at": None,
        "username": username,
        "full_name": full_name,
    }


class AdminReviewModerationTest(unittest.IsolatedAsyncioTestCase):
    def test_task_081_i18n_contains_admin_review_keys(self):
        keys = [
            "admin_reviews_help",
            "admin_reviews_report_title",
            "admin_reviews_report_empty",
            "admin_review_details_title",
            "admin_review_status_updated",
            "admin_review_command_error",
            "admin_review_status_pending",
            "admin_review_status_published",
            "admin_review_status_rejected",
        ]
        for language in SUPPORTED_LANGUAGES:
            for key in keys:
                self.assertTrue(t(key, language))

    def test_task_081_parses_admin_review_commands(self):
        self.assertEqual(("pending", 10), parse_admin_reviews_command("/reviews"))
        self.assertEqual(("published", 5), parse_admin_reviews_command("/reviews published 5"))
        self.assertEqual(("all", 50), parse_admin_reviews_command("/reviews all 999"))
        self.assertEqual(7, parse_admin_review_command("/review 7"))
        self.assertEqual((7, "published"), parse_admin_review_status_command("/review_status 7 published"))
        self.assertEqual((7, "rejected"), parse_admin_review_status_command("/review_status 7 rejected"))
        for invalid in ["/reviews bad", "/reviews pending 0", "/review", "/review x", "/review_status 7 pending"]:
            with self.assertRaises(AdminReviewError):
                if invalid.startswith("/review_status"):
                    parse_admin_review_status_command(invalid)
                elif invalid.startswith("/review ") or invalid == "/review":
                    parse_admin_review_command(invalid)
                else:
                    parse_admin_reviews_command(invalid)

    async def test_task_081_repository_lists_details_and_updates_reviews(self):
        db = FakeDatabase()
        repo = ReviewsRepository(db)

        rows = await repo.list_for_moderation(status="pending", limit=10)
        details = await repo.review_details(7)
        locked = await repo.lock_review_for_moderation(7, expected_status="pending")
        updated = await repo.set_status(7, "published")

        self.assertEqual(db.reviews, rows)
        self.assertEqual(7, details["id"])
        self.assertEqual(7, locked["id"])
        self.assertEqual("published", updated["status"])
        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("FROM reviews r", queries)
        self.assertIn("LEFT JOIN users", queries)
        self.assertIn("FOR UPDATE", queries)
        self.assertIn("UPDATE reviews", queries)
        self.assertNotIn("%s", queries)

    async def test_task_081_service_lists_details_and_moderates_pending_reviews_only(self):
        db = FakeDatabase()
        service = AdminReviewsService(FakePool(db))

        rows = await service.list_reviews(status="pending", limit=10)
        details = await service.get_review_details(7)
        updated = await service.set_review_status(review_id=7, status="published")

        self.assertEqual(db.reviews, rows)
        self.assertEqual(7, details["id"])
        self.assertEqual("published", updated["status"])

        db.detail = review_row(status="published")
        with self.assertRaises(AdminReviewError):
            await service.set_review_status(review_id=7, status="rejected")
        with self.assertRaises(AdminReviewError):
            await service.set_review_status(review_id=7, status="pending")

    def test_task_081_formats_reports_with_html_escaping(self):
        rows = [review_row(text="<script>x</script>", username="evil<name>")]
        report = format_admin_reviews_report(rows, status="pending", language="ru")
        details = format_admin_review_details(
            review_row(text="<b>Очень вкусно</b>", username=None, full_name="Ann & Bob"),
            language="ru",
        )

        self.assertIn(t("admin_reviews_report_title", "ru", status="pending"), report)
        self.assertIn("#7", report)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", report)
        self.assertIn("@evil&lt;name&gt;", report)
        self.assertIn(t("admin_review_details_title", "ru", review_id=7), details)
        self.assertIn("&lt;b&gt;Очень вкусно&lt;/b&gt;", details)
        self.assertIn("Ann &amp; Bob", details)

    async def test_task_081_handlers_require_admin_chat_and_answer_reports(self):
        db = FakeDatabase()
        pool = FakePool(db)
        cfg = config()

        non_admin = FakeMessage("/reviews", chat_id=1)
        await handle_admin_review_list(non_admin, pool, cfg)
        self.assertEqual(t("admin_only", "ru"), non_admin.answers[-1][0])

        menu = FakeMessage(t("admin_menu_reviews", "ru"))
        await handle_admin_reviews_menu(menu, pool, cfg)
        self.assertIn("/reviews", menu.answers[-1][0])

        list_msg = FakeMessage("/reviews pending 5")
        await handle_admin_review_list(list_msg, pool, cfg)
        self.assertIn("#7", list_msg.answers[-1][0])
        self.assertIn("reply_markup", list_msg.answers[-1][1])

        detail_msg = FakeMessage("/review 7")
        await handle_admin_review_detail(detail_msg, pool, cfg)
        self.assertIn(t("admin_review_details_title", "ru", review_id=7), detail_msg.answers[-1][0])

        status_msg = FakeMessage("/review_status 7 published")
        await handle_admin_review_status(status_msg, pool, cfg)
        self.assertIn("#7", status_msg.answers[-1][0])
        self.assertIn("published", status_msg.answers[-1][0])

        error_msg = FakeMessage("/review_status 7 pending")
        await handle_admin_review_status(error_msg, pool, cfg)
        self.assertEqual(t("admin_review_command_error", "ru"), error_msg.answers[-1][0])
