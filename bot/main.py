"""Application entry point for the PranaNew Telegram booking bot."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import Config, load_config

RunPollingFunc = Callable[[Bot, Dispatcher], Awaitable[None]]


def create_bot(config: Config) -> Bot:
    """Create a configured aiogram Bot instance."""

    return Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_client_router() -> Router:
    """Create client-facing handlers available in the MVP runtime."""

    router = Router(name="client")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer("Бот PranaNew запущен. Бронирование слотов будет добавлено далее.")

    return router


def create_dispatcher(*routers: Router) -> Dispatcher:
    """Create Dispatcher and include provided routers.

    If no routers are provided, the default client router is registered.
    """

    dispatcher = Dispatcher()
    for router in routers or (create_client_router(),):
        dispatcher.include_router(router)
    return dispatcher


async def run_polling(bot: Bot, dispatcher: Dispatcher) -> None:
    """Reset webhook state and start Telegram long polling."""

    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


def main(
    env_path: str | Path = ".env",
    run_polling_func: RunPollingFunc = run_polling,
) -> None:
    """CLI entrypoint used by `python -m bot.main`."""

    config = load_config(env_path)
    bot = create_bot(config)
    dispatcher = create_dispatcher()
    asyncio.run(run_polling_func(bot, dispatcher))


if __name__ == "__main__":
    main()
