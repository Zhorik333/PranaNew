"""Shared repository primitives."""

from __future__ import annotations

from typing import Any, Protocol


class DatabaseExecutor(Protocol):
    """Subset of asyncpg pool/connection methods used by repositories."""

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a SQL statement."""

    async def fetchrow(self, query: str, *args: Any) -> Any:
        """Fetch one row."""

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        """Fetch many rows."""

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Fetch one scalar value."""


class BaseRepository:
    """Base class for repositories backed by an asyncpg-like executor."""

    def __init__(self, db: DatabaseExecutor) -> None:
        self.db = db
