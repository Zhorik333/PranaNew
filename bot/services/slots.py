"""Slot listing service for client booking flow."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from bot.repositories.slots import SlotsRepository
from bot.services.booking_validation import (
    BookingValidationError,
    calculate_last_slot_time as calculate_validated_last_slot_time,
    validate_slot_selection,
)

SLOT_CALLBACK_PREFIX = "slot:"
BOOKING_PREVIEW_CALLBACK_PREFIX = "preview:"
BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX = "confirm_booking:"
BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX = "change_booking:"
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


def _format_selected_ids(selected_slot_ids: list[int]) -> str:
    return ",".join(str(slot_id) for slot_id in selected_slot_ids)


def _parse_selected_ids(payload: str) -> list[int]:
    return [int(item) for item in payload.split(",") if item]


def build_booking_preview_callback_data(selected_slot_ids: list[int]) -> str:
    """Build callback data for opening the booking preview screen."""

    if not selected_slot_ids:
        raise ValueError("Selected slots cannot be empty")
    return f"{BOOKING_PREVIEW_CALLBACK_PREFIX}{_format_selected_ids(selected_slot_ids)}"


def build_booking_preview_confirm_callback_data(selected_slot_ids: list[int]) -> str:
    """Build callback data for future booking confirmation."""

    if not selected_slot_ids:
        raise ValueError("Selected slots cannot be empty")
    return f"{BOOKING_PREVIEW_CONFIRM_CALLBACK_PREFIX}{_format_selected_ids(selected_slot_ids)}"


def build_booking_preview_change_callback_data(selected_slot_ids: list[int]) -> str:
    """Build callback data for returning from preview to slot selection."""

    if not selected_slot_ids:
        raise ValueError("Selected slots cannot be empty")
    return f"{BOOKING_PREVIEW_CHANGE_CALLBACK_PREFIX}{_format_selected_ids(selected_slot_ids)}"


def parse_booking_preview_callback_data(callback_data: str, *, prefix: str = BOOKING_PREVIEW_CALLBACK_PREFIX) -> list[int]:
    """Parse preview/change/confirm callback data into selected slot ids."""

    if not callback_data.startswith(prefix):
        raise ValueError("Invalid booking preview callback data")
    selected_slot_ids = _parse_selected_ids(callback_data.removeprefix(prefix))
    if not selected_slot_ids:
        raise ValueError("Selected slots cannot be empty")
    return selected_slot_ids


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
    if not candidate_slots:
        return []
    try:
        ordered_slots = validate_slot_selection(candidate_slots, max_consecutive=max_consecutive)
    except BookingValidationError as error:
        raise SlotSelectionError(str(error)) from error

    return [slot_id(slot) for slot in ordered_slots]


def selected_slots(
    available_slots: list[Any],
    selected_slot_ids: list[int],
    *,
    max_consecutive: int = DEFAULT_MAX_CONSECUTIVE_SLOTS,
) -> list[Any]:
    """Return selected available slots sorted by time."""

    if not selected_slot_ids:
        raise SlotSelectionError("preview_empty_selection")
    available_by_id = {slot_id(slot): slot for slot in available_slots}
    try:
        slots = [available_by_id[selected_slot_id] for selected_slot_id in selected_slot_ids]
    except KeyError as error:
        raise SlotSelectionError("slot_unavailable") from error
    try:
        return validate_slot_selection(slots, max_consecutive=max_consecutive)
    except BookingValidationError as error:
        error_key = "preview_empty_selection" if str(error) == "empty_selection" else str(error)
        raise SlotSelectionError(error_key) from error


def pickup_time(available_slots: list[Any], selected_slot_ids: list[int]) -> time:
    """Return pickup time for a selected chain: the start time of the last slot."""

    slots = selected_slots(available_slots, selected_slot_ids)
    return calculate_validated_last_slot_time(slots)


def format_booking_preview_text(available_slots: list[Any], selected_slot_ids: list[int], language: str) -> str:
    """Format selected slots and pickup time for the booking preview screen."""

    from bot.i18n import t

    slots = selected_slots(available_slots, selected_slot_ids)
    slot_lines = "\n".join(f"• {format_slot_label(slot)}" for slot in slots)
    pickup = _slot_start(slots[-1]).strftime("%H:%M")
    return f"{t('preview_title', language)}\n\n{slot_lines}\n\n{t('pickup_time', language, time=pickup)}"


async def list_available_slots(db, *, now: datetime | None = None) -> list[Any]:
    """Return future available slots sorted by time."""

    current_time = now or datetime.now(timezone.utc)
    return list(await SlotsRepository(db).list_available_future(current_time))
