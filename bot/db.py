"""Database connection helpers for the PranaNew Telegram booking bot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

import asyncpg


class DatabaseConnectionError(RuntimeError):
    """Raised when the bot cannot create a PostgreSQL connection pool."""


class ClosablePool(Protocol):
    """Minimal protocol required from an asyncpg pool-like object."""

    async def close(self) -> None:
        """Close all resources owned by the pool."""


PoolT = TypeVar("PoolT", bound=ClosablePool)
PoolFactory = Callable[..., Awaitable[PoolT]]
DEFAULT_POOL_FACTORY = asyncpg.create_pool


async def create_pool(
    database_url: str,
    *,
    pool_factory: PoolFactory[PoolT] = DEFAULT_POOL_FACTORY,
) -> PoolT:
    """Create an async PostgreSQL connection pool from DATABASE_URL.

    The raised error intentionally avoids including the DATABASE_URL because it may
    contain credentials.
    """

    connection_failed = False
    try:
        return await pool_factory(dsn=database_url)
    except Exception:
        connection_failed = True

    if connection_failed:
        raise DatabaseConnectionError(
            "Could not connect to PostgreSQL database. "
            "Check DATABASE_URL and PostgreSQL availability."
        )

    raise AssertionError("unreachable database connection state")


async def close_pool(pool: ClosablePool | None) -> None:
    """Close a pool if one was created."""

    if pool is not None:
        await pool.close()
