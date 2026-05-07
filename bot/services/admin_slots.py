"""Admin slot management parsing, formatting, and service helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.i18n import t
from bot.repositories.slots import SlotsRepository


class AdminSlotError(ValueError):
    """Raised when an admin slot command is invalid."""


@dataclass(frozen=True)
class SlotSpec:
    """One generated slot ready to be persisted."""

    slot_date: date
    starts_at: time
    start_time: datetime
    duration_minutes: int
    capacity: int


def generate_slot_specs(
    slot_date: date,
    step_minutes: int,
    start_at: time,
    end_at: time,
    capacity: int,
    tz_name: str,
) -> list[SlotSpec]:
    """Generate inclusive slot specs from start to end using the requested step."""

    if step_minutes <= 0:
        raise AdminSlotError("invalid_step")
    if capacity <= 0:
        raise AdminSlotError("invalid_capacity")
    if end_at < start_at:
        raise AdminSlotError("invalid_period")
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise AdminSlotError("invalid_timezone") from exc

    current = datetime.combine(slot_date, start_at, tzinfo=tz)
    end = datetime.combine(slot_date, end_at, tzinfo=tz)
    specs: list[SlotSpec] = []
    while current <= end:
        specs.append(
            SlotSpec(
                slot_date=slot_date,
                starts_at=current.time().replace(tzinfo=None),
                start_time=current,
                duration_minutes=step_minutes,
                capacity=capacity,
            )
        )
        current += timedelta(minutes=step_minutes)
    return specs


def parse_generate_slots_command(text: str) -> tuple[date, int, time, time, int]:
    """Parse /generate DATE STEP START END [CAPACITY]."""

    parts = text.split()
    if len(parts) not in {5, 6}:
        raise AdminSlotError("invalid_generate_command")
    try:
        slot_date = date.fromisoformat(parts[1])
        step_minutes = int(parts[2])
        start_at = time.fromisoformat(parts[3])
        end_at = time.fromisoformat(parts[4])
        capacity = int(parts[5]) if len(parts) == 6 else 1
    except ValueError as exc:
        raise AdminSlotError("invalid_generate_command") from exc
    return slot_date, step_minutes, start_at, end_at, capacity


def parse_list_slots_command(text: str) -> date:
    """Parse /admin_slots DATE."""

    parts = text.split()
    if len(parts) != 2:
        raise AdminSlotError("invalid_list_command")
    try:
        return date.fromisoformat(parts[1])
    except ValueError as exc:
        raise AdminSlotError("invalid_list_command") from exc


def parse_block_slot_command(text: str) -> int:
    """Parse /block_slot ID or /unblock_slot ID."""

    parts = text.split()
    if len(parts) != 2:
        raise AdminSlotError("invalid_slot_id")
    try:
        slot_id = int(parts[1])
    except ValueError as exc:
        raise AdminSlotError("invalid_slot_id") from exc
    if slot_id <= 0:
        raise AdminSlotError("invalid_slot_id")
    return slot_id


def parse_capacity_command(text: str) -> tuple[int, int]:
    """Parse /set_capacity ID CAPACITY."""

    parts = text.split()
    if len(parts) != 3:
        raise AdminSlotError("invalid_capacity_command")
    try:
        slot_id = int(parts[1])
        capacity = int(parts[2])
    except ValueError as exc:
        raise AdminSlotError("invalid_capacity_command") from exc
    if slot_id <= 0:
        raise AdminSlotError("invalid_slot_id")
    if capacity <= 0:
        raise AdminSlotError("invalid_capacity")
    return slot_id, capacity


def _slot_value(slot: Any, key: str) -> Any:
    if isinstance(slot, dict):
        return slot[key]
    try:
        return slot[key]
    except (KeyError, TypeError):
        return getattr(slot, key)


def format_admin_slots_report(slot_date: date, slots: list[Any], *, language: str) -> str:
    """Format all slots for an admin date report."""

    if not slots:
        return t("admin_slots_report_empty", language, slot_date=slot_date.isoformat())

    lines = [t("admin_slots_report_title", language, slot_date=slot_date.isoformat())]
    for slot in slots:
        starts_at = _slot_value(slot, "starts_at")
        capacity = int(_slot_value(slot, "capacity"))
        booked_count = int(_slot_value(slot, "booked_count"))
        completed_count = int(_slot_value(slot, "completed_count"))
        is_blocked = bool(_slot_value(slot, "is_blocked"))
        if is_blocked:
            status = t("admin_slot_status_blocked", language)
        elif completed_count:
            status = f"{t('admin_slot_status_completed', language)} {booked_count}/{capacity} ✅"
        elif booked_count:
            status = f"{t('admin_slot_status_booked', language)} {booked_count}/{capacity}"
        else:
            status = f"{t('admin_slot_status_free', language)} {booked_count}/{capacity}"
        lines.append(f"#{_slot_value(slot, 'id')} {starts_at:%H:%M} {status}")
    return "\n".join(lines)


class AdminSlotsService:
    """Application service for admin slot management."""

    def __init__(self, db):
        self.db = db

    async def generate_slots(
        self,
        *,
        slot_date: date,
        step_minutes: int,
        start_at: time,
        end_at: time,
        capacity: int,
        tz_name: str,
    ) -> int:
        specs = generate_slot_specs(slot_date, step_minutes, start_at, end_at, capacity, tz_name)
        repository = SlotsRepository(self.db)
        created = 0
        for spec in specs:
            row = await repository.create_slot_ignore_duplicate(
                slot_date=spec.slot_date,
                starts_at=spec.starts_at,
                start_time=spec.start_time,
                duration_minutes=spec.duration_minutes,
                capacity=spec.capacity,
            )
            if row is not None:
                created += 1
        return created

    async def list_slots_report(self, slot_date: date, *, language: str) -> str:
        slots = list(await SlotsRepository(self.db).list_by_date_with_occupancy(slot_date))
        return format_admin_slots_report(slot_date, slots, language=language)

    async def set_blocked(self, *, slot_id: int, is_blocked: bool) -> None:
        updated = await SlotsRepository(self.db).set_blocked(slot_id=slot_id, is_blocked=is_blocked)
        if not updated:
            raise AdminSlotError("slot_not_found")

    async def set_capacity(self, *, slot_id: int, capacity: int) -> None:
        if capacity <= 0:
            raise AdminSlotError("invalid_capacity")
        updated = await SlotsRepository(self.db).set_capacity(slot_id=slot_id, capacity=capacity)
        if not updated:
            raise AdminSlotError("slot_not_found_or_capacity_below_occupancy")
