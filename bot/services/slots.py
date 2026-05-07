"""Slot listing service for client booking flow."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from bot.repositories.slots import SlotsRepository

SLOT_CALLBACK_PREFIX = "slot:"
DEFAULT_MAX_CONSECUTIVE_SLOTS = 5


class SlotSelectionError(ValueError):
    """Raised when slot selection violates booking rules."""


def parse_slot_callback_data(callback_data: str) -> tuple[int, list[int]]:
    """Parse callback data in the form slot:<clicked_id>|<selected_id_csv>."""

    if not callback_data.startswith(SLOT_CALLBACK_PREFIX):
        raise ValueError("Invalid slot callback data")
    payload = callback_data.removeprefix(SLOT_CALLBACK_PREFIX)
    clicked_raw, _, selected_raw = payload.partition("|")
    clicked_slot_id = int(clicked_raw)
    selected_slot_ids = [int(item) for item in selected_raw.split(",") if item]
    return clicked_slot_id, selected_slot_ids


def build_slot_callback_data(clicked_slot_id: int, selected_slot_ids: list[int] | None = None) -> str:
    """Build compact callback data for a slot button."""

    selected = ",".join(str(slot_id) for slot_id in (selected_slot_ids or []))
    return f"{SLOT_CALLBACK_PREFIX}{clicked_slot_id}|{selected}"


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


def slot_id(slot: Any) -> int:
    """Return a slot id from a dict, asyncpg Record, or object."""

    return int(_slot_value(slot, "id"))


def _slot_start(slot: Any) -> datetime:
    try:
        start_time = _slot_value(slot, "start_time")
        if isinstance(start_time, datetime):
            return start_time
    except (KeyError, AttributeError):
        pass
    slot_date = _slot_value(slot, "slot_date")
    starts_at = _slot_value(slot, "starts_at")
    if not isinstance(starts_at, time):
        raise TypeError("Slot starts_at must be a time value")
    return datetime.combine(slot_date, starts_at)


def _duration_minutes(slot: Any) -> int:
    try:
        return int(_slot_value(slot, "duration_minutes"))
    except (KeyError, AttributeError):
        return 10


def _are_consecutive(slots: list[Any]) -> bool:
    if len(slots) < 2:
        return True
    ordered = sorted(slots, key=_slot_start)
    for previous, current in zip(ordered, ordered[1:]):
        expected_next = _slot_start(previous) + timedelta(minutes=_duration_minutes(previous))
        if _slot_start(current) != expected_next:
            return False
    return True


def toggle_slot_selection(
    available_slots: list[Any],
    *,
    selected_slot_ids: list[int],
    clicked_slot_id: int,
    max_consecutive: int = DEFAULT_MAX_CONSECUTIVE_SLOTS,
) -> list[int]:
    """Toggle a slot while enforcing availability, max count, and consecutiveness."""

    available_by_id = {slot_id(slot): slot for slot in available_slots}
    if clicked_slot_id not in available_by_id:
        raise SlotSelectionError("slot_unavailable")

    current_selection = [slot_id for slot_id in selected_slot_ids if slot_id in available_by_id]
    if clicked_slot_id in current_selection:
        candidate_ids = [slot_id for slot_id in current_selection if slot_id != clicked_slot_id]
    else:
        candidate_ids = [*current_selection, clicked_slot_id]

    if len(candidate_ids) > max_consecutive:
        raise SlotSelectionError("max_consecutive")

    candidate_slots = [available_by_id[slot_id] for slot_id in candidate_ids]
    if not _are_consecutive(candidate_slots):
        raise SlotSelectionError("non_consecutive")

    return [slot_id(slot) for slot in sorted(candidate_slots, key=_slot_start)]


async def list_available_slots(db, *, now: datetime | None = None) -> list[Any]:
    """Return future available slots sorted by time."""

    current_time = now or datetime.now(timezone.utc)
    return list(await SlotsRepository(db).list_available_future(current_time))
