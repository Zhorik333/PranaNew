import unittest

from bot.config import Config
from bot.db import DatabaseConnectionError, close_pool, create_pool


TEST_DATABASE_URL = "postgresql://db-user@127.0.0.1:5432/prananew"


class FakePool:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class DatabaseConnectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_task_007_create_pool_uses_configured_database_url(self):
        calls = []
        expected_pool = FakePool()

        async def fake_pool_factory(**kwargs):
            calls.append(kwargs)
            return expected_pool

        pool = await create_pool(
            TEST_DATABASE_URL,
            pool_factory=fake_pool_factory,
        )

        self.assertIs(expected_pool, pool)
        self.assertEqual([{"dsn": TEST_DATABASE_URL}], calls)

    async def test_task_007_create_pool_wraps_connection_errors_with_clear_message(self):
        async def failing_pool_factory(**kwargs):
            raise OSError(f"network unreachable for {TEST_DATABASE_URL}")

        with self.assertRaisesRegex(
            DatabaseConnectionError,
            "Could not connect to PostgreSQL database",
        ) as context:
            await create_pool(
                TEST_DATABASE_URL,
                pool_factory=failing_pool_factory,
            )

        self.assertIsNone(context.exception.__cause__)
        self.assertIsNone(context.exception.__context__)
        self.assertNotIn(TEST_DATABASE_URL, str(context.exception))

    async def test_task_007_close_pool_closes_existing_pool(self):
        pool = FakePool()

        await close_pool(pool)

        self.assertTrue(pool.closed)

    async def test_task_007_close_pool_ignores_missing_pool(self):
        await close_pool(None)

    def test_task_007_config_still_exposes_database_url(self):
        config = Config(
            bot_token="123456:ABCDEF",
            database_url=TEST_DATABASE_URL,
            admin_chat_id=-1001234567890,
        )

        self.assertEqual(TEST_DATABASE_URL, config.database_url)


if __name__ == "__main__":
    unittest.main()
