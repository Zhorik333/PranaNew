"""Pure validation helpers for selected booking slots."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

DEFAULT_MAX_CONSECUTIVE_SLOTS = 5


class BookingValidationError(ValueError):
    """Raised when selected slots do not satisfy booking rules."""


def slot_value(slot: Any, key: str) -> Any:
    """Read a slot field from asyncpg Record, dict, or simple object."""

    if isinstance(slot, dict):
        return slot[key]
    try:
        return slot[key]
    except (KeyError, TypeError):
        return getattr(slot, key)


def slot_id(slot: Any) -> int:
    """Return a slot id from a dict, asyncpg Record, or object."""

    return int(slot_value(slot, "id"))


def slot_start(slot: Any) -> datetime:
    """Return a combined datetime for a slot start."""

    try:
        start_time = slot_value(slot, "start_time")
        if isinstance(start_time, datetime):
            return start_time
    except (KeyError, AttributeError):
        pass
    slot_date = slot_value(slot, "slot_date")
    starts_at = slot_value(slot, "starts_at")
    if not isinstance(starts_at, time):
        raise TypeError("Slot starts_at must be a time value")
    return datetime.combine(slot_date, starts_at)


def slot_duration_minutes(slot: Any) -> int:
    """Return configured slot duration, defaulting to 10 minutes."""

    try:
        return int(slot_value(slot, "duration_minutes"))
    except (KeyError, AttributeError):
        return 10


def validate_non_empty_selection(slots: list[Any]) -> list[Any]:
    """Reject empty selected slot lists."""

    if not slots:
        raise BookingValidationError("empty_selection")
    return slots


def validate_max_consecutive(slots: list[Any], max_consecutive: int = DEFAULT_MAX_CONSECUTIVE_SLOTS) -> list[Any]:
    """Reject selections above the configured max consecutive slot count."""

    if max_consecutive <= 0:
        raise BookingValidationError("invalid_max_consecutive")
    if len(slots) > max_consecutive:
        raise BookingValidationError("max_consecutive")
    return slots


def validate_slots_are_consecutive(slots: list[Any]) -> list[Any]:
    """Reject duplicate and non-adjacent selected slots, returning them sorted by time."""

    validate_non_empty_selection(slots)
    ids = [slot_id(slot) for slot in slots]
    if len(ids) != len(set(ids)):
        raise BookingValidationError("duplicate_slot")

    ordered = sorted(slots, key=slot_start)
    for previous, current in zip(ordered, ordered[1:]):
        expected_next = slot_start(previous) + timedelta(minutes=slot_duration_minutes(previous))
        if slot_start(current) != expected_next:
            raise BookingValidationError("non_consecutive")
    return ordered


def calculate_last_slot_time(slots: list[Any]) -> time:
    """Return pickup time: the start time of the last selected slot by chronology."""

    ordered = validate_slots_are_consecutive(slots)
    return slot_start(ordered[-1]).time()


def validate_slot_selection(
    slots: list[Any],
    *,
    max_consecutive: int = DEFAULT_MAX_CONSECUTIVE_SLOTS,
) -> list[Any]:
    """Run all pure booking slot selection validation rules."""

    validate_non_empty_selection(slots)
    validate_max_consecutive(slots, max_consecutive=max_consecutive)
    return validate_slots_are_consecutive(slots)
