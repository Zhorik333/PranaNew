from pathlib import Path
import re
import subprocess
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "migrations" / "001_init.sql"
SCHEMA_PATH = PROJECT_ROOT / "docs" / "database_schema.sql"
PSQL = "/home/arts9/.local/pgsql/bin/psql"


class InitialMigrationTest(unittest.TestCase):
    def _migration(self) -> str:
        self.assertTrue(
            MIGRATION_PATH.exists(),
            "TASK-006 must create migrations/001_init.sql",
        )
        return MIGRATION_PATH.read_text(encoding="utf-8")

    def _normalized_migration(self) -> str:
        return re.sub(r"\s+", " ", self._migration().lower())

    def test_task_006_migration_exists_and_documents_replay_policy(self):
        migration = self._normalized_migration()

        self.assertIn("task-006", migration)
        self.assertIn("one-time migration", migration)

    def test_task_006_migration_contains_schema_tables(self):
        migration = self._normalized_migration()

        for table_name in (
            "users",
            "settings",
            "slots",
            "bookings",
            "booking_slots",
            "reviews",
            "i18n_texts",
            "scheduler_jobs",
        ):
            with self.subTest(table_name=table_name):
                self.assertIn(f"create table {table_name}", migration)

    def test_task_006_migration_keeps_task_005_design_constraints(self):
        migration = self._normalized_migration()

        expected_fragments = (
            "references users(tg_id)",
            "references bookings(id)",
            "references slots(id)",
            "primary key (booking_id, slot_id)",
            "unique (slot_date, starts_at)",
            "unique (booking_id)",
            "check (status in ('active', 'completed', 'cancelled'))",
            "check (status in ('pending', 'published', 'rejected'))",
            "check (rating is null or rating between 1 and 5)",
            "idx_slots_date_starts_at",
            "idx_booking_slots_slot_id",
            "idx_bookings_user_id_status",
        )
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, migration)

    def test_task_006_migration_matches_schema_design(self):
        self.assertTrue(SCHEMA_PATH.exists(), "TASK-005 schema design must exist")
        self.assertEqual(
            SCHEMA_PATH.read_text(encoding="utf-8").strip(),
            self._migration().strip(),
            "Initial migration should be the reviewed TASK-005 schema design",
        )

    def test_task_006_migration_applies_to_empty_postgresql_schema(self):
        if not Path(PSQL).exists():
            self.skipTest("Local PostgreSQL psql binary is unavailable")

        sql = f"""
BEGIN;
CREATE SCHEMA task006_check;
SET search_path TO task006_check;
\\i {MIGRATION_PATH}
ROLLBACK;
"""
        result = subprocess.run(
            [
                PSQL,
                "-h",
                "/home/arts9/.local/pgsql-run",
                "-p",
                "5432",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
            ],
            input=sql,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )
        self.assertIn("CREATE TABLE", result.stdout)
        self.assertIn("ROLLBACK", result.stdout)


if __name__ == "__main__":
    unittest.main()
