"""Rate limiting middleware for basic anti-spam protection."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from bot.i18n import t

DEFAULT_RATE_LIMIT_MAX_EVENTS = 6
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 3.0


class RateLimiter:
    """Small in-memory sliding-window rate limiter scoped by key."""

    def __init__(
        self,
        *,
        max_events: int = DEFAULT_RATE_LIMIT_MAX_EVENTS,
        window_seconds: float = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Return True when the key is still inside the allowed request rate."""

        now = self.clock()
        cutoff = now - self.window_seconds
        timestamps = self._events[key]
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= self.max_events:
            return False
        timestamps.append(now)
        return True


class RateLimitMiddleware(BaseMiddleware):
    """Drop excessive user messages/callbacks and send a localized notice."""

    def __init__(
        self,
        *,
        max_events: int = DEFAULT_RATE_LIMIT_MAX_EVENTS,
        window_seconds: float = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.limiter = RateLimiter(max_events=max_events, window_seconds=window_seconds, clock=clock)

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        if self._is_admin_chat(event, data):
            return await handler(event, data)
        key = self._rate_limit_key(event)
        if key is None or self.limiter.allow(key):
            return await handler(event, data)
        await self._answer_rate_limited(event)
        return None

    def _rate_limit_key(self, event: Any) -> str | None:
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        if user_id is None:
            return None
        return f"tg:{int(user_id)}"

    def _is_admin_chat(self, event: Any, data: dict[str, Any]) -> bool:
        config = data.get("config")
        admin_chat_id = getattr(config, "admin_chat_id", None)
        if admin_chat_id is None:
            return False
        message = event.message if isinstance(event, CallbackQuery) else event
        chat = getattr(message, "chat", None)
        return getattr(chat, "id", None) == admin_chat_id

    async def _answer_rate_limited(self, event: Any) -> None:
        text = t("rate_limit_exceeded", "ru")
        if isinstance(event, CallbackQuery) or hasattr(event, "answer") and hasattr(event, "message"):
            await event.answer(text, show_alert=True)
            return
        if isinstance(event, Message) or hasattr(event, "answer"):
            await event.answer(text)
