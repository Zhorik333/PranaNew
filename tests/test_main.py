import inspect
import unittest
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Config
from bot.main import create_bot, create_dispatcher, main, run_application, run_polling
from bot.routers.admin import create_admin_router
from bot.routers.client import create_client_router


class MainRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def make_config(self) -> Config:
        return Config(
            bot_token="123456:ABCDEF",
            database_url="postgresql://db-user@127.0.0.1:5432/prananew",
            admin_chat_id=-1001234567890,
        )

    def test_task_004_create_bot_uses_configured_token_and_html_parse_mode(self):
        bot = create_bot(self.make_config())

        self.assertIsInstance(bot, Bot)
        self.assertEqual("123456:ABCDEF", bot.token)
        self.assertIsInstance(bot.default, DefaultBotProperties)
        self.assertEqual(ParseMode.HTML, bot.default.parse_mode)

    def test_task_004_create_dispatcher_returns_dispatcher_with_router(self):
        router = Router(name="test-router")

        dispatcher = create_dispatcher(router)

        self.assertIsInstance(dispatcher, Dispatcher)
        self.assertEqual([router], dispatcher.sub_routers)

    def test_task_052_default_dispatcher_includes_client_and_admin_routers(self):
        dispatcher = create_dispatcher()
        router_names = [router.name for router in dispatcher.sub_routers]

        self.assertEqual([create_client_router().name, create_admin_router().name], router_names)

    async def test_task_004_run_polling_deletes_webhook_and_starts_polling(self):
        dispatcher = create_dispatcher(Router(name="test-router"))
        dispatcher.start_polling = AsyncMock()
        bot = create_bot(self.make_config())
        bot.delete_webhook = AsyncMock()

        await run_polling(bot, dispatcher)

        bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
        dispatcher.start_polling.assert_awaited_once_with(bot)

    def test_task_004_main_loads_config_creates_runtime_and_runs_polling(self):
        calls = []
        pools = []

        class FakePool:
            async def close(self):
                pools.append("closed")

        async def fake_pool_factory(**kwargs):
            pools.append(kwargs)
            return FakePool()

        async def fake_run_polling(bot, dispatcher):
            calls.append((bot, dispatcher))

        main(
            env_path=".env.example",
            run_polling_func=fake_run_polling,
            pool_factory=fake_pool_factory,
        )

        self.assertEqual(1, len(calls))
        bot, dispatcher = calls[0]
        self.assertIsInstance(bot, Bot)
        self.assertIsInstance(dispatcher, Dispatcher)
        self.assertIn("db_pool", dispatcher.workflow_data)
        self.assertIn("dsn", pools[0])
        self.assertTrue(pools[0]["dsn"].startswith("postgresql://"))
        self.assertTrue(pools[0]["dsn"].endswith("@127.0.0.1:5432/prananew"))
        self.assertEqual("closed", pools[-1])

    async def test_task_007_run_application_closes_pool_when_polling_fails(self):
        pools = []

        class FakePool:
            async def close(self):
                pools.append("closed")

        async def fake_pool_factory(**kwargs):
            pools.append(kwargs)
            return FakePool()

        async def failing_run_polling(bot, dispatcher):
            self.assertIn("db_pool", dispatcher.workflow_data)
            raise RuntimeError("polling failed")

        with self.assertRaisesRegex(RuntimeError, "polling failed"):
            await run_application(
                self.make_config(),
                run_polling_func=failing_run_polling,
                pool_factory=fake_pool_factory,
            )

        self.assertEqual("closed", pools[-1])

    async def test_task_007_run_application_closes_bot_session_when_pool_creation_fails(self):
        class FakeBot:
            def __init__(self):
                self.session = type("FakeSession", (), {"close": AsyncMock()})()

        fake_bot = FakeBot()

        async def failing_pool_factory(**kwargs):
            raise OSError("database unavailable")

        async def unused_run_polling(bot, dispatcher):
            raise AssertionError("polling must not start when pool creation fails")

        with patch("bot.main.create_bot", return_value=fake_bot):
            with self.assertRaisesRegex(Exception, "Could not connect to PostgreSQL database"):
                await run_application(
                    self.make_config(),
                    run_polling_func=unused_run_polling,
                    pool_factory=failing_pool_factory,
                )

        fake_bot.session.close.assert_awaited_once_with()

    async def test_task_007_run_application_closes_bot_session_when_pool_close_fails(self):
        class FakeBot:
            def __init__(self):
                self.session = type("FakeSession", (), {"close": AsyncMock()})()

        class FailingClosePool:
            async def close(self):
                raise RuntimeError("pool close failed")

        fake_bot = FakeBot()

        async def fake_pool_factory(**kwargs):
            return FailingClosePool()

        async def fake_run_polling(bot, dispatcher):
            return None

        with patch("bot.main.create_bot", return_value=fake_bot):
            with self.assertRaisesRegex(RuntimeError, "pool close failed"):
                await run_application(
                    self.make_config(),
                    run_polling_func=fake_run_polling,
                    pool_factory=fake_pool_factory,
                )

        fake_bot.session.close.assert_awaited_once_with()

    def test_task_004_main_function_is_sync_cli_entrypoint(self):
        self.assertFalse(inspect.iscoroutinefunction(main))


if __name__ == "__main__":
    unittest.main()
