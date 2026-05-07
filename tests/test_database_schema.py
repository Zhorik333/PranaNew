from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "docs" / "database_schema.sql"


class DatabaseSchemaTest(unittest.TestCase):
    def _schema(self) -> str:
        self.assertTrue(
            SCHEMA_PATH.exists(),
            "TASK-005 must provide a PostgreSQL DDL design at docs/database_schema.sql",
        )
        return SCHEMA_PATH.read_text(encoding="utf-8")

    def _normalized_schema(self) -> str:
        return re.sub(r"\s+", " ", self._schema().lower())

    def test_task_005_schema_defines_required_tables(self):
        schema = self._normalized_schema()

        for table_name in (
            "users",
            "slots",
            "bookings",
            "booking_slots",
            "reviews",
            "settings",
            "i18n_texts",
        ):
            with self.subTest(table_name=table_name):
                self.assertIn(f"create table {table_name}", schema)

    def test_task_005_schema_uses_foreign_keys_for_relationships(self):
        schema = self._normalized_schema()

        expected_relationships = (
            "references users(tg_id)",
            "references bookings(id)",
            "references slots(id)",
        )
        for relationship in expected_relationships:
            with self.subTest(relationship=relationship):
                self.assertIn(relationship, schema)

    def test_task_005_schema_has_constraints_for_statuses_and_positive_values(self):
        schema = self._normalized_schema()

        self.assertRegex(
            schema,
            r"bookings.*status.*check.*active.*completed.*cancelled",
        )
        self.assertRegex(
            schema,
            r"reviews.*status.*check.*pending.*published.*rejected",
        )
        self.assertRegex(schema, r"capacity integer not null.*check \(capacity > 0\)")
        self.assertRegex(schema, r"duration_minutes integer not null.*check \(duration_minutes > 0\)")
        self.assertRegex(schema, r"rating integer.*check.*between 1 and 5")

    def test_task_005_schema_has_uniqueness_to_prevent_duplicates(self):
        schema = self._normalized_schema()

        expected_unique_constraints = (
            "primary key (booking_id, slot_id)",
            "unique (slot_date, starts_at)",
            "unique (booking_id)",
            "primary key (key)",
            "primary key (language, key)",
        )
        for constraint in expected_unique_constraints:
            with self.subTest(constraint=constraint):
                self.assertIn(constraint, schema)

    def test_task_005_schema_has_indexes_for_frequent_queries(self):
        schema = self._normalized_schema()

        expected_indexes = (
            "idx_slots_date_starts_at",
            "idx_booking_slots_slot_id",
            "idx_bookings_user_id_status",
            "idx_bookings_status_created_at",
            "idx_reviews_status_created_at",
        )
        for index_name in expected_indexes:
            with self.subTest(index_name=index_name):
                self.assertIn(f"create index {index_name}", schema)

    def test_task_005_schema_does_not_use_booked_count_as_source_of_truth(self):
        schema = self._normalized_schema()

        self.assertNotIn("booked_count", schema)
        self.assertIn("availability is calculated from booking_slots", schema)


if __name__ == "__main__":
    unittest.main()
