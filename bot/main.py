"""Application entry point for the PranaNew Telegram booking bot."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Config, load_config
from bot.db import DEFAULT_POOL_FACTORY, PoolFactory, close_pool, create_pool
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.routers.admin import create_admin_router
from bot.routers.client import create_client_router
from bot.services.review_scheduler import start_review_request_scheduler
from bot.structured_logging import configure_structured_logging, get_structured_logger, log_event

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
    rate_limit_middleware = RateLimitMiddleware()
    dispatcher.message.middleware(rate_limit_middleware)
    dispatcher.callback_query.middleware(rate_limit_middleware)
    dispatcher.workflow_data["rate_limit_enabled"] = True
    dispatcher.workflow_data["rate_limit_middleware"] = rate_limit_middleware
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
    logger: logging.Logger | None = None,
) -> None:
    """Create runtime resources, run polling, and close resources on shutdown."""

    logger = logger or get_structured_logger()
    log_event(logger, logging.INFO, "bot_starting", admin_chat_id=config.admin_chat_id)
    bot = create_bot(config)
    dispatcher = create_dispatcher()
    pool = None
    scheduler_task = None

    try:
        try:
            pool = await create_pool(config.database_url, pool_factory=pool_factory)
        except Exception:
            log_event(logger, logging.ERROR, "database_error", exc_info=True)
            raise
        dispatcher.workflow_data["db_pool"] = pool
        dispatcher.workflow_data["config"] = config
        scheduler_task = start_review_request_scheduler(pool, bot, poll_interval_seconds=30)
        log_event(logger, logging.INFO, "bot_polling_starting", admin_chat_id=config.admin_chat_id)
        await asyncio.sleep(0)
        try:
            await run_polling_func(bot, dispatcher)
        except Exception:
            log_event(logger, logging.ERROR, "telegram_api_error", exc_info=True)
            raise
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await close_pool(pool)
        finally:
            await bot.session.close()
            log_event(logger, logging.INFO, "bot_stopped", admin_chat_id=config.admin_chat_id)


def main(
    env_path: str | Path = ".env",
    run_polling_func: RunPollingFunc = run_polling,
    pool_factory: PoolFactory = DEFAULT_POOL_FACTORY,
) -> None:
    """CLI entrypoint used by `python -m bot.main`."""

    config = load_config(env_path)
    logger = configure_structured_logging(level=config.log_level)
    asyncio.run(
        run_application(
            config,
            run_polling_func=run_polling_func,
            pool_factory=pool_factory,
            logger=logger,
        )
    )


if __name__ == "__main__":
    main()
