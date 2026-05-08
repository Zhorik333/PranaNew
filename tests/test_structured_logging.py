import io
import json
import logging
import unittest
from unittest.mock import AsyncMock, patch

from bot.config import Config
from bot.main import run_application
from bot.services.bookings import BookingService
from bot.structured_logging import configure_structured_logging, log_event
from tests.test_booking_confirmation import FakeConnection, FakePool, slot


SAMPLE_BOT_CREDENTIAL = "123456" + ":" + ("A" * 24)
SAMPLE_DATABASE_URL = "postgresql://" + "db_user:hidden-value@127.0.0.1:5432/prananew"


class StructuredLoggingTest(unittest.IsolatedAsyncioTestCase):
    def make_config(self) -> Config:
        return Config(
            bot_token=SAMPLE_BOT_CREDENTIAL,
            database_url=SAMPLE_DATABASE_URL,
            admin_chat_id=-1001234567890,
            log_level="INFO",
        )

    def test_task_090_logs_json_events_and_redacts_sensitive_context(self):
        stream = io.StringIO()
        logger = configure_structured_logging(level="INFO", stream=stream)

        log_event(
            logger,
            logging.INFO,
            "config_loaded",
            bot_token=SAMPLE_BOT_CREDENTIAL,
            database_url=SAMPLE_DATABASE_URL,
            admin_chat_id=-1001234567890,
        )

        raw_line = stream.getvalue().strip()
        payload = json.loads(raw_line)
        self.assertEqual("config_loaded", payload["event"])
        self.assertEqual("INFO", payload["level"])
        self.assertEqual(-1001234567890, payload["admin_chat_id"])
        self.assertEqual("[REDACTED]", payload["bot_token"])
        self.assertEqual("[REDACTED]", payload["database_url"])
        self.assertNotIn("A" * 24, raw_line)
        self.assertNotIn("hidden-value", raw_line)
        self.assertNotIn("postgresql://", raw_line)

    def test_task_090_redacts_secrets_from_exception_messages(self):
        stream = io.StringIO()
        logger = configure_structured_logging(level="INFO", stream=stream)

        try:
            raise RuntimeError(f"could not connect using {SAMPLE_DATABASE_URL} with credential {SAMPLE_BOT_CREDENTIAL}")
        except RuntimeError:
            log_event(logger, logging.ERROR, "database_error", exc_info=True, database_url=SAMPLE_DATABASE_URL)

        raw_line = stream.getvalue().strip()
        payload = json.loads(raw_line)
        self.assertEqual("database_error", payload["event"])
        self.assertEqual("ERROR", payload["level"])
        self.assertIn("exception", payload)
        self.assertNotIn("secret_password", raw_line)
        self.assertNotIn("ABCDEF_FAKE_TOKEN_REPLACE_ME", raw_line)
        self.assertNotIn("postgresql://", raw_line)

    async def test_task_090_run_application_logs_lifecycle_and_failures_without_secrets(self):
        stream = io.StringIO()
        logger = configure_structured_logging(level="INFO", stream=stream)

        class FakeBot:
            def __init__(self):
                self.session = type("FakeSession", (), {"close": AsyncMock()})()

        fake_bot = FakeBot()

        async def failing_pool_factory(**kwargs):
            raise OSError(f"database unavailable: {kwargs['dsn']}")

        async def unused_run_polling(bot, dispatcher):
            raise AssertionError("polling must not start")

        with patch("bot.main.create_bot", return_value=fake_bot):
            with self.assertRaisesRegex(Exception, "Could not connect to PostgreSQL database"):
                await run_application(
                    self.make_config(),
                    run_polling_func=unused_run_polling,
                    pool_factory=failing_pool_factory,
                    logger=logger,
                )

        fake_bot.session.close.assert_awaited_once_with()
        lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
        events = [line["event"] for line in lines]
        self.assertIn("bot_starting", events)
        self.assertIn("database_error", events)
        self.assertIn("bot_stopped", events)
        raw_logs = stream.getvalue()
        self.assertNotIn("secret_password", raw_logs)
        self.assertNotIn("ABCDEF_FAKE_TOKEN_REPLACE_ME", raw_logs)
        self.assertNotIn("postgresql://", raw_logs)

    async def test_task_090_booking_service_logs_booking_creation_event(self):
        stream = io.StringIO()
        logger = configure_structured_logging(level="INFO", stream=stream)
        connection = FakeConnection()
        connection.locked_slots = [slot(10, 14, 0), slot(11, 14, 10)]
        connection.capacity_counts = [{"slot_id": 10, "booked_count": 0}, {"slot_id": 11, "booked_count": 0}]

        booking_id = await BookingService(FakePool(connection), logger=logger).create_booking(
            user_id=42,
            selected_slot_ids=[10, 11],
        )

        self.assertEqual(700, booking_id)
        lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
        self.assertEqual("booking_created", lines[-1]["event"])
        self.assertEqual(700, lines[-1]["booking_id"])
        self.assertEqual(42, lines[-1]["user_id"])
        self.assertEqual([10, 11], lines[-1]["slot_ids"])


if __name__ == "__main__":
    unittest.main()
