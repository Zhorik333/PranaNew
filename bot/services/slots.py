"""Slot listing service for client booking flow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.repositories.slots import SlotsRepository

SLOT_CALLBACK_PREFIX = "slot:"


def _slot_value(slot: Any, key: str) -> Any:
    """Read a slot field from asyncpg Record, dict, or simple object."""

    if isinstance(slot, dict):
        return slot[key]
    try:
        return slot[key]
    except (KeyError, TypeError):
        return getattr(slot, key)


def format_slot_label(slot: Any) -> str:
    """Format a slot as a compact date/time inline button label."""

    slot_date = _slot_value(slot, "slot_date")
    starts_at = _slot_value(slot, "starts_at")
    return f"{slot_date:%d.%m} {starts_at:%H:%M}"


async def list_available_slots(db, *, now: datetime | None = None) -> list[Any]:
    """Return future available slots sorted by time."""

    current_time = now or datetime.now(timezone.utc)
    return list(await SlotsRepository(db).list_available_future(current_time))
