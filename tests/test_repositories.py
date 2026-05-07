import unittest
from datetime import date, time, timezone, datetime
from pathlib import Path

from bot.repositories import (
    BookingsRepository,
    ReviewsRepository,
    SettingsRepository,
    SlotsRepository,
    UsersRepository,
)


class FakeDatabase:
    def __init__(self):
        self.calls = []
        self.fetchrow_result = None
        self.fetch_result = []
        self.fetchval_result = None

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE 1"

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_result

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.fetch_result

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return self.fetchval_result


def last_query(fake_db):
    return fake_db.calls[-1][1]


def last_args(fake_db):
    return fake_db.calls[-1][2]


class RepositoryLayerTest(unittest.IsolatedAsyncioTestCase):
    async def test_task_008_users_repository_upserts_and_fetches_users(self):
        db = FakeDatabase()
        db.fetchrow_result = {"tg_id": 42, "language": "ru"}
        repository = UsersRepository(db)

        await repository.upsert_user(
            tg_id=42,
            username="alice",
            first_name="Alice",
            last_name="Tester",
            language="en",
        )
        user = await repository.get_by_tg_id(42)

        self.assertEqual({"tg_id": 42, "language": "ru"}, user)
        self.assertIn("INSERT INTO users", db.calls[0][1])
        self.assertIn("ON CONFLICT (tg_id) DO UPDATE", db.calls[0][1])
        self.assertEqual((42, "alice", "Alice", "Tester", "en"), db.calls[0][2])
        self.assertIn("SELECT", db.calls[1][1])
        self.assertIn("FROM users", db.calls[1][1])
        self.assertEqual((42,), db.calls[1][2])

    async def test_task_008_settings_repository_gets_and_sets_values(self):
        db = FakeDatabase()
        db.fetchval_result = "Europe/Belgrade"
        repository = SettingsRepository(db)

        await repository.set("default_tz", "Europe/Belgrade")
        value = await repository.get("default_tz", default="ru")
        missing = await repository.get("missing", default="fallback")

        self.assertEqual("Europe/Belgrade", value)
        self.assertEqual("Europe/Belgrade", missing)
        self.assertIn("INSERT INTO settings", db.calls[0][1])
        self.assertIn("ON CONFLICT (key) DO UPDATE", db.calls[0][1])
        self.assertEqual(("default_tz", "Europe/Belgrade"), db.calls[0][2])
        self.assertIn("SELECT value", db.calls[1][1])
        self.assertEqual(("default_tz",), db.calls[1][2])

    async def test_task_008_slots_repository_creates_and_lists_available_slots(self):
        db = FakeDatabase()
        db.fetchrow_result = {"id": 10}
        db.fetch_result = [{"id": 10, "booked_count": 0}]
        repository = SlotsRepository(db)
        start = datetime(2026, 5, 8, 14, 0, tzinfo=timezone.utc)

        slot = await repository.create_slot(
            slot_date=date(2026, 5, 8),
            starts_at=time(14, 0),
            start_time=start,
            duration_minutes=10,
            capacity=2,
        )
        available = await repository.list_available(date(2026, 5, 8))

        self.assertEqual({"id": 10}, slot)
        self.assertEqual([{"id": 10, "booked_count": 0}], available)
        self.assertIn("INSERT INTO slots", db.calls[0][1])
        self.assertEqual((date(2026, 5, 8), time(14, 0), start, 10, 2), db.calls[0][2])
        self.assertIn("LEFT JOIN booking_slots", db.calls[1][1])
        self.assertIn("LEFT JOIN bookings", db.calls[1][1])
        self.assertIn("b.status IN ('active', 'completed')", db.calls[1][1])
        self.assertNotIn("s.booked_count", db.calls[1][1])

    async def test_task_008_bookings_repository_creates_booking_and_links_slots(self):
        db = FakeDatabase()
        db.fetchval_result = 77
        repository = BookingsRepository(db)
        pickup = datetime(2026, 5, 8, 14, 20, tzinfo=timezone.utc)

        booking_id = await repository.create_booking(
            user_id=42,
            slot_ids=[10, 11, 12],
            customer_name="Alice",
            customer_phone="+382000000",
            comment="no onion",
            pickup_time=pickup,
        )

        self.assertEqual(77, booking_id)
        self.assertIn("INSERT INTO bookings", db.calls[0][1])
        self.assertEqual((42, "active", "Alice", "no onion", pickup), (*db.calls[0][2][:3], db.calls[0][2][4], db.calls[0][2][5]))
        self.assertEqual(4, len(db.calls))
        self.assertTrue(all("INSERT INTO booking_slots" in call[1] for call in db.calls[1:]))
        self.assertEqual((77, 10), db.calls[1][2])
        self.assertEqual((77, 12), db.calls[3][2])

    async def test_task_008_reviews_repository_creates_and_lists_published_reviews(self):
        db = FakeDatabase()
        db.fetchrow_result = {"id": 5, "status": "pending"}
        db.fetch_result = [{"id": 6, "status": "published"}]
        repository = ReviewsRepository(db)

        review = await repository.create_review(
            booking_id=77,
            user_id=42,
            text="Great pizza",
            rating=5,
        )
        published = await repository.list_published(limit=10)

        self.assertEqual({"id": 5, "status": "pending"}, review)
        self.assertEqual([{"id": 6, "status": "published"}], published)
        self.assertIn("INSERT INTO reviews", db.calls[0][1])
        self.assertEqual((77, 42, "Great pizza", 5), db.calls[0][2])
        self.assertIn("WHERE status = 'published'", db.calls[1][1])
        self.assertEqual((10,), db.calls[1][2])

    def test_task_008_telegram_runtime_does_not_embed_repository_sql(self):
        runtime_files = [
            Path("bot/main.py"),
            *Path("bot/routers").glob("*.py"),
        ]

        for path in runtime_files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("SELECT ", text, path.as_posix())
            self.assertNotIn("INSERT INTO", text, path.as_posix())
            self.assertNotIn("UPDATE ", text, path.as_posix())
            self.assertNotIn("DELETE FROM", text, path.as_posix())


if __name__ == "__main__":
    unittest.main()
