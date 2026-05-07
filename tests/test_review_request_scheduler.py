import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from aiogram.types import InlineKeyboardMarkup

from bot.config import Config
from bot.i18n import t
from bot.keyboards.admin import review_request_keyboard
from bot.main import run_application
from bot.services.bookings import BookingService
from bot.services.review_scheduler import ReviewRequestScheduler, start_review_request_scheduler


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
    def __init__(self, connection=None):
        self.connection = connection or FakeConnection()
        self.closed = False

    def acquire(self):
        self.connection.events.append("acquire_called")
        return FakeAcquire(self)

    async def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.events = []
        self.calls = []
        self.pending_job = None
        self.running_job = None
        self.last_error = None

    def transaction(self):
        self.events.append("transaction_called")
        return FakeTransaction(self)

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "UPDATE scheduler_jobs" in query and "RETURNING id, payload" in query:
            if self.pending_job is None:
                return None
            self.running_job = dict(self.pending_job)
            self.pending_job = None
            return dict(self.running_job)
        return None

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        if "SET status = 'done'" in query:
            self.running_job = None
        if "SET status = 'pending'" in query:
            if self.running_job is not None:
                self.pending_job = dict(self.running_job)
                self.running_job = None
            self.last_error = args[1]
        return "EXECUTE 1"

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return None


class FakeBot:
    def __init__(self):
        self.sent_messages = []
        self.session = type("FakeSession", (), {"close": AsyncMock()})()

    async def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append((chat_id, text, kwargs))


class FailingBot(FakeBot):
    async def send_message(self, chat_id, text, **kwargs):
        raise RuntimeError("telegram send failed")


def make_config() -> Config:
    return Config(
        **{
            "bot_" + "token": "123456:ABCDEF",
            "database_url": "postgresql://prananew:***@127.0.0.1:5432/prananew",
            "admin_chat_id": -100123,
        }
    )


class ReviewRequestSchedulerTest(unittest.IsolatedAsyncioTestCase):
    async def test_task_060_service_claims_oldest_due_review_request_job(self):
        connection = FakeConnection()
        connection.pending_job = {"id": 55, "payload": {"booking_id": 700, "user_id": 42}}

        job = await BookingService(FakePool(connection)).claim_due_review_request()

        self.assertEqual({"job_id": 55, "booking_id": 700, "user_id": 42}, job)
        self.assertIn("commit", connection.events)
        queries = "\n".join(call[1] for call in connection.calls)
        self.assertIn("job_type = 'review_request'", queries)
        self.assertIn("status = 'pending'", queries)
        self.assertIn("run_at <= now()", queries)
        self.assertIn("status = 'running'", queries)
        self.assertIn("updated_at <= now() - interval '5 minutes'", queries)
        self.assertIn("FOR UPDATE SKIP LOCKED", queries)
        self.assertIn("RETURNING id, payload", queries)

    async def test_task_060_service_decodes_asyncpg_jsonb_string_payload(self):
        connection = FakeConnection()
        connection.pending_job = {"id": 55, "payload": json.dumps({"booking_id": 700, "user_id": 42})}

        job = await BookingService(FakePool(connection)).claim_due_review_request()

        self.assertEqual({"job_id": 55, "booking_id": 700, "user_id": 42}, job)

    async def test_task_060_service_returns_none_when_no_due_job_exists(self):
        connection = FakeConnection()

        job = await BookingService(FakePool(connection)).claim_due_review_request()

        self.assertIsNone(job)
        self.assertIn("commit", connection.events)

    async def test_task_060_scheduler_sends_review_request_and_marks_job_done(self):
        connection = FakeConnection()
        connection.pending_job = {"id": 55, "payload": {"booking_id": 700, "user_id": 42}}
        bot = FakeBot()

        processed = await ReviewRequestScheduler(FakePool(connection), bot, language="ru").run_once()

        self.assertTrue(processed)
        self.assertEqual(1, len(bot.sent_messages))
        chat_id, text, kwargs = bot.sent_messages[0]
        self.assertEqual(42, chat_id)
        self.assertEqual(t("review_request", "ru"), text)
        self.assertIsInstance(kwargs["reply_markup"], InlineKeyboardMarkup)
        self.assertEqual(review_request_keyboard(700, language="ru").inline_keyboard[0][0].callback_data, kwargs["reply_markup"].inline_keyboard[0][0].callback_data)
        self.assertIsNone(connection.running_job)
        self.assertTrue(any("SET status = 'done'" in call[1] for call in connection.calls))
        done_args = [call[2] for call in connection.calls if "SET status = 'done'" in call[1]][0]
        self.assertEqual((55,), done_args)

    async def test_task_060_scheduler_restores_pending_job_when_telegram_send_fails(self):
        connection = FakeConnection()
        connection.pending_job = {"id": 55, "payload": {"booking_id": 700, "user_id": 42}}

        processed = await ReviewRequestScheduler(FakePool(connection), FailingBot(), language="ru").run_once()

        self.assertTrue(processed)
        self.assertIsNotNone(connection.pending_job)
        self.assertEqual(55, connection.pending_job["id"])
        self.assertIn("telegram_send_failed", connection.last_error)
        self.assertTrue(any("SET status = 'pending'" in call[1] for call in connection.calls))
        restore_query = [call[1] for call in connection.calls if "SET status = 'pending'" in call[1]][0]
        self.assertIn("run_at = now() + interval '5 minutes'", restore_query)

    async def test_task_060_scheduler_ignores_malformed_payload_and_restores_job(self):
        connection = FakeConnection()
        connection.pending_job = {"id": 55, "payload": {"booking_id": 700}}
        bot = FakeBot()

        processed = await ReviewRequestScheduler(FakePool(connection), bot, language="ru").run_once()

        self.assertTrue(processed)
        self.assertEqual([], bot.sent_messages)
        self.assertIsNotNone(connection.pending_job)
        self.assertIn("invalid_review_request_payload", connection.last_error)

    async def test_task_060_start_scheduler_returns_background_task_and_can_be_cancelled(self):
        task = start_review_request_scheduler(FakePool(), FakeBot(), poll_interval_seconds=0.01)
        self.assertIsInstance(task, asyncio.Task)

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_task_060_run_application_starts_and_cancels_scheduler_with_polling_lifecycle(self):
        pool = FakePool()
        scheduler_task = None
        events = []

        async def fake_pool_factory(**kwargs):
            return pool

        async def fake_run_polling(bot, dispatcher):
            events.append("polling_started")
            self.assertIn("db_pool", dispatcher.workflow_data)
            self.assertIn("config", dispatcher.workflow_data)

        async def fake_scheduler_worker():
            events.append("scheduler_started")
            try:
                await asyncio.sleep(3600)
            finally:
                events.append("scheduler_cancelled")

        def fake_start_scheduler(db_pool, bot, *, poll_interval_seconds):
            nonlocal scheduler_task
            self.assertIs(db_pool, pool)
            self.assertEqual(30, poll_interval_seconds)
            scheduler_task = asyncio.create_task(fake_scheduler_worker())
            return scheduler_task

        with patch("bot.main.create_bot", return_value=FakeBot()):
            with patch("bot.main.start_review_request_scheduler", side_effect=fake_start_scheduler):
                await run_application(
                    make_config(),
                    run_polling_func=fake_run_polling,
                    pool_factory=fake_pool_factory,
                )

        self.assertEqual(["scheduler_started", "polling_started", "scheduler_cancelled"], events)
        self.assertTrue(scheduler_task.cancelled())
        self.assertTrue(pool.closed)

    async def test_task_060_run_application_cleanup_ignores_failed_scheduler_task_and_closes_resources(self):
        pool = FakePool()
        scheduler_task = None

        async def fake_pool_factory(**kwargs):
            return pool

        async def fake_run_polling(bot, dispatcher):
            await asyncio.sleep(0)

        async def failing_scheduler_worker():
            raise RuntimeError("scheduler failed")

        def fake_start_scheduler(db_pool, bot, *, poll_interval_seconds):
            nonlocal scheduler_task
            scheduler_task = asyncio.create_task(failing_scheduler_worker())
            return scheduler_task

        fake_bot = FakeBot()
        with patch("bot.main.create_bot", return_value=fake_bot):
            with patch("bot.main.start_review_request_scheduler", side_effect=fake_start_scheduler):
                await run_application(
                    make_config(),
                    run_polling_func=fake_run_polling,
                    pool_factory=fake_pool_factory,
                )

        self.assertTrue(scheduler_task.done())
        self.assertTrue(pool.closed)
        fake_bot.session.close.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
