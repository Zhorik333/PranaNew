"""Application entry point for the PranaNew Telegram booking bot."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Config, load_config
from bot.db import DEFAULT_POOL_FACTORY, PoolFactory, close_pool, create_pool
from bot.routers.admin import create_admin_router
from bot.routers.client import create_client_router

RunPollingFunc = Callable[[Bot, Dispatcher], Awaitable[None]]


def create_bot(config: Config) -> Bot:
    """Create a configured aiogram Bot instance."""

    return Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )



def create_dispatcher(*routers: Router) -> Dispatcher:
    """Create Dispatcher and include provided routers.

    If no routers are provided, the default client router is registered.
    """

    dispatcher = Dispatcher()
    for router in routers or (create_client_router(), create_admin_router()):
        dispatcher.include_router(router)
    return dispatcher


async def run_polling(bot: Bot, dispatcher: Dispatcher) -> None:
    """Reset webhook state and start Telegram long polling."""

    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


async def run_application(
    config: Config,
    *,
    run_polling_func: RunPollingFunc = run_polling,
    pool_factory: PoolFactory = DEFAULT_POOL_FACTORY,
) -> None:
    """Create runtime resources, run polling, and close resources on shutdown."""

    bot = create_bot(config)
    dispatcher = create_dispatcher()
    pool = None

    try:
        pool = await create_pool(config.database_url, pool_factory=pool_factory)
        dispatcher.workflow_data["db_pool"] = pool
        dispatcher.workflow_data["config"] = config
        await run_polling_func(bot, dispatcher)
    finally:
        try:
            await close_pool(pool)
        finally:
            await bot.session.close()


def main(
    env_path: str | Path = ".env",
    run_polling_func: RunPollingFunc = run_polling,
    pool_factory: PoolFactory = DEFAULT_POOL_FACTORY,
) -> None:
    """CLI entrypoint used by `python -m bot.main`."""

    config = load_config(env_path)
    asyncio.run(
        run_application(
            config,
            run_polling_func=run_polling_func,
            pool_factory=pool_factory,
        )
    )


if __name__ == "__main__":
    main()
