import inspect
import unittest
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Config
from bot.main import create_bot, create_dispatcher, main, run_polling


class MainRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def make_config(self) -> Config:
        return Config(
            bot_token="123456:ABCDEF",
            database_url="postgresql://user:pass@127.0.0.1:5432/prananew",
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
        self.assertIn(router, dispatcher.sub_routers)

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

        async def fake_run_polling(bot, dispatcher):
            calls.append((bot, dispatcher))

        main(
            env_path=".env.example",
            run_polling_func=fake_run_polling,
        )

        self.assertEqual(1, len(calls))
        bot, dispatcher = calls[0]
        self.assertIsInstance(bot, Bot)
        self.assertIsInstance(dispatcher, Dispatcher)

    def test_task_004_main_function_is_sync_cli_entrypoint(self):
        self.assertFalse(inspect.iscoroutinefunction(main))


if __name__ == "__main__":
    unittest.main()
