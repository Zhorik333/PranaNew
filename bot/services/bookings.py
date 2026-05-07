"""Atomic booking creation service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bot.repositories.bookings import BookingsRepository
from bot.repositories.slots import SlotsRepository
from bot.services.booking_validation import BookingValidationError, validate_slot_selection

DEFAULT_BOOKING_STATUS = "active"


class BookingCreationError(ValueError):
    """Raised when a booking cannot be created from selected slots."""


class BookingCancellationError(ValueError):
    """Raised when a booking cannot be cancelled."""


def _slot_value(slot: Any, key: str) -> Any:
    if isinstance(slot, dict):
        return slot[key]
    try:
        return slot[key]
    except (KeyError, TypeError):
        return getattr(slot, key)


def _slot_id(slot: Any) -> int:
    return int(_slot_value(slot, "id"))


def _slot_capacity(slot: Any) -> int:
    return int(_slot_value(slot, "capacity"))


def _slot_is_blocked(slot: Any) -> bool:
    return bool(_slot_value(slot, "is_blocked"))


def _slot_start(slot: Any) -> datetime:
    start_time = _slot_value(slot, "start_time")
    if not isinstance(start_time, datetime):
        raise TypeError("Slot start_time must be a datetime value")
    return start_time


def _count_row_slot_id(row: Any) -> int:
    return int(_slot_value(row, "slot_id"))


def _count_row_booked_count(row: Any) -> int:
    return int(_slot_value(row, "booked_count"))


class BookingService:
    """Creates and cancels bookings atomically against an asyncpg-like pool."""

    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def cancel_booking(self, *, user_id: int, booking_id: int, cancellation_reason: str | None = None) -> bool:
        """Cancel an active booking, preserving history and freeing its slots.

        Returns True when the call changed an active booking to cancelled and
        False when the booking was already cancelled. Missing/foreign bookings
        and completed bookings are rejected inside the same transaction.
        """

        if booking_id <= 0:
            raise BookingCancellationError("booking_not_found")

        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                bookings_repository = BookingsRepository(connection)
                booking = await bookings_repository.get_by_id_for_update(booking_id)
                if booking is None or int(_slot_value(booking, "user_id")) != int(user_id):
                    raise BookingCancellationError("booking_not_found")

                status = str(_slot_value(booking, "status"))
                if status == "cancelled":
                    return False
                if status != "active":
                    raise BookingCancellationError("booking_cannot_cancel")

                await bookings_repository.set_status(
                    booking_id,
                    "cancelled",
                    cancellation_reason=cancellation_reason,
                )
                return True

    async def create_booking(self, *, user_id: int, selected_slot_ids: list[int]) -> int:
        """Create or return an idempotent active booking for selected slots.

        The selected slot rows are locked inside the transaction before existence,
        blocked-state, capacity, and sequence checks. This makes a repeated confirm
        callback idempotent and prevents overbooking when another booking appears
        between preview and confirmation.
        """

        if not selected_slot_ids:
            raise BookingCreationError("empty_selection")
        if len(set(selected_slot_ids)) != len(selected_slot_ids):
            raise BookingCreationError("duplicate_slots")

        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                slots_repository = SlotsRepository(connection)
                bookings_repository = BookingsRepository(connection)

                locked_slots = list(await slots_repository.get_by_ids_for_update(selected_slot_ids))
                if len(locked_slots) != len(selected_slot_ids):
                    raise BookingCreationError("slot_unavailable")
                if any(_slot_is_blocked(slot) for slot in locked_slots):
                    raise BookingCreationError("slot_unavailable")

                try:
                    ordered_slots = validate_slot_selection(locked_slots)
                except BookingValidationError as error:
                    raise BookingCreationError(str(error)) from error

                ordered_slot_ids = [_slot_id(slot) for slot in ordered_slots]
                existing_booking_id = await bookings_repository.find_active_by_user_and_slot_ids(
                    user_id=user_id,
                    slot_ids=ordered_slot_ids,
                )
                if existing_booking_id is not None:
                    return int(existing_booking_id)

                count_rows = await bookings_repository.count_consuming_bookings_by_slot_ids(ordered_slot_ids)
                booked_by_slot_id = {_count_row_slot_id(row): _count_row_booked_count(row) for row in count_rows}
                for slot in ordered_slots:
                    if booked_by_slot_id.get(_slot_id(slot), 0) >= _slot_capacity(slot):
                        raise BookingCreationError("slot_full")

                pickup_datetime = _slot_start(ordered_slots[-1])
                return int(
                    await bookings_repository.create_booking(
                        user_id=user_id,
                        slot_ids=ordered_slot_ids,
                        status=DEFAULT_BOOKING_STATUS,
                        customer_name=None,
                        customer_phone=None,
                        comment="",
                        pickup_time=pickup_datetime,
                    )
                )
