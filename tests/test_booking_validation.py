import unittest
from datetime import date, time

from bot.services.booking_validation import (
    BookingValidationError,
    calculate_last_slot_time,
    validate_max_consecutive,
    validate_non_empty_selection,
    validate_slots_are_consecutive,
    validate_slot_selection,
)


def slot(slot_id, hour, minute, *, duration=10, slot_date=date(2026, 5, 8)):
    return {
        "id": slot_id,
        "slot_date": slot_date,
        "starts_at": time(hour, minute),
        "duration_minutes": duration,
    }


class BookingValidationTest(unittest.TestCase):
    def test_task_045_rejects_empty_selection(self):
        with self.assertRaisesRegex(BookingValidationError, "empty_selection"):
            validate_non_empty_selection([])

    def test_task_045_rejects_selection_above_limit(self):
        selected = [slot(10, 14, 0), slot(11, 14, 10), slot(12, 14, 20)]

        with self.assertRaisesRegex(BookingValidationError, "max_consecutive"):
            validate_max_consecutive(selected, max_consecutive=2)

    def test_task_045_rejects_invalid_limit(self):
        with self.assertRaisesRegex(BookingValidationError, "invalid_max_consecutive"):
            validate_max_consecutive([slot(10, 14, 0)], max_consecutive=0)

    def test_task_045_accepts_consecutive_slots_even_when_input_is_unsorted(self):
        selected = [slot(12, 14, 20), slot(10, 14, 0), slot(11, 14, 10)]

        ordered = validate_slots_are_consecutive(selected)

        self.assertEqual([10, 11, 12], [item["id"] for item in ordered])

    def test_task_045_rejects_non_adjacent_slots(self):
        selected = [slot(10, 14, 0), slot(12, 14, 20)]

        with self.assertRaisesRegex(BookingValidationError, "non_consecutive"):
            validate_slots_are_consecutive(selected)

    def test_task_045_rejects_duplicate_slot_ids(self):
        selected = [slot(10, 14, 0), slot(10, 14, 0)]

        with self.assertRaisesRegex(BookingValidationError, "duplicate_slot"):
            validate_slots_are_consecutive(selected)

    def test_task_045_uses_each_slot_duration_to_check_next_start(self):
        selected = [slot(10, 14, 0, duration=20), slot(11, 14, 20, duration=10)]

        ordered = validate_slots_are_consecutive(selected)

        self.assertEqual([10, 11], [item["id"] for item in ordered])

    def test_task_045_calculates_pickup_time_as_last_selected_slot_start_time(self):
        selected = [slot(10, 14, 0), slot(12, 14, 20), slot(11, 14, 10)]

        self.assertEqual(time(14, 20), calculate_last_slot_time(selected))

    def test_task_045_full_validation_returns_ordered_slots(self):
        selected = [slot(11, 14, 10), slot(10, 14, 0)]

        ordered = validate_slot_selection(selected, max_consecutive=5)

        self.assertEqual([10, 11], [item["id"] for item in ordered])


if __name__ == "__main__":
    unittest.main()
