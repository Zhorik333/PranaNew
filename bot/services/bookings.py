"""Atomic booking creation service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bot.repositories.bookings import BookingsRepository
from bot.repositories.slots import SlotsRepository
from bot.services.booking_validation import BookingValidationError, validate_slot_selection

DEFAULT_BOOKING_STATUS = "active"
BOOKING_COMPLETE_CALLBACK_PREFIX = "complete_booking:"
REVIEW_REQUEST_CALLBACK_PREFIX = "leave_review:"


def build_booking_complete_callback_data(booking_id: int) -> str:
    """Build callback data for admin completion of a booking."""

    if booking_id <= 0:
        raise ValueError("Booking id must be positive")
    return f"{BOOKING_COMPLETE_CALLBACK_PREFIX}{booking_id}"


def parse_booking_complete_callback_data(callback_data: str) -> int:
    """Parse admin complete callback data into a booking id."""

    if not callback_data.startswith(BOOKING_COMPLETE_CALLBACK_PREFIX):
        raise ValueError("Invalid booking complete callback data")
    booking_id = int(callback_data.removeprefix(BOOKING_COMPLETE_CALLBACK_PREFIX))
    if booking_id <= 0:
        raise ValueError("Booking id must be positive")
    return booking_id


def build_review_request_callback_data(booking_id: int) -> str:
    """Build callback data for future review flow."""

    if booking_id <= 0:
        raise ValueError("Booking id must be positive")
    return f"{REVIEW_REQUEST_CALLBACK_PREFIX}{booking_id}"


class BookingCreationError(ValueError):
    """Raised when a booking cannot be created from selected slots."""


class BookingCancellationError(ValueError):
    """Raised when a booking cannot be cancelled."""


class BookingCompletionError(ValueError):
    """Raised when a booking cannot be marked completed."""


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
    """Creates and manages bookings atomically against an asyncpg-like pool."""

    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def get_admin_notification_details(self, *, booking_id: int) -> Any:
        """Fetch compact booking details for an admin-group notification."""

        if booking_id <= 0:
            raise BookingCreationError("booking_not_found")
        async with self.db_pool.acquire() as connection:
            return await BookingsRepository(connection).get_admin_notification_details(booking_id)

    async def complete_booking(self, *, booking_id: int) -> dict[str, int | bool]:
        """Mark an active booking as completed and return user notification data."""

        if booking_id <= 0:
            raise BookingCompletionError("booking_not_found")

        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                bookings_repository = BookingsRepository(connection)
                booking = await bookings_repository.get_by_id_for_update(booking_id)
                if booking is None:
                    raise BookingCompletionError("booking_not_found")

                user_id = int(_slot_value(booking, "user_id"))
                status = str(_slot_value(booking, "status"))
                if status == "completed":
                    return {
                        "booking_id": int(booking_id),
                        "user_id": user_id,
                        "changed": False,
                        "review_request_pending": await bookings_repository.has_pending_review_request_job(booking_id),
                    }
                if status != "active":
                    raise BookingCompletionError("booking_cannot_complete")

                await bookings_repository.set_status(booking_id, "completed")
                await bookings_repository.create_review_request_job(booking_id=booking_id, user_id=user_id)
                return {
                    "booking_id": int(booking_id),
                    "user_id": user_id,
                    "changed": True,
                    "review_request_pending": True,
                }

    async def claim_review_request(self, *, booking_id: int) -> bool:
        """Atomically claim a pending review request notification for sending."""

        if booking_id <= 0:
            raise BookingCompletionError("booking_not_found")

        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                return await BookingsRepository(connection).claim_pending_review_request_job(booking_id)

    async def mark_review_request_sent(self, *, booking_id: int) -> None:
        """Mark a pending review request notification as sent."""

        if booking_id <= 0:
            raise BookingCompletionError("booking_not_found")

        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                await BookingsRepository(connection).mark_review_request_job_done(booking_id)

    async def restore_review_request_retry(self, *, booking_id: int, error: str = "telegram_send_failed") -> None:
        """Restore a claimed review request notification so it can be retried."""

        if booking_id <= 0:
            raise BookingCompletionError("booking_not_found")

        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                await BookingsRepository(connection).restore_review_request_job_pending(
                    booking_id,
                    error[:200],
                )

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
