import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from aiogram.types import ReplyKeyboardMarkup

from bot.config import Config
from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.repositories.slots import SlotsRepository
from bot.routers.admin import (
    handle_admin_slot_block,
    handle_admin_slot_generate,
    handle_admin_slot_list,
    handle_admin_slot_unblock,
    handle_admin_slot_capacity,
    handle_admin_generate_slots_menu,
    handle_admin_booked_slots_menu,
)
from bot.services.admin_slots import (
    AdminSlotError,
    format_admin_slots_report,
    generate_slot_specs,
    parse_block_slot_command,
    parse_capacity_command,
    parse_generate_slots_command,
    parse_list_slots_command,
)


class FakeChat:
    def __init__(self, id):
        self.id = id


class FakeMessage:
    def __init__(self, *, chat_id=-100123, text=""):
        self.chat = FakeChat(chat_id)
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


def make_config(admin_chat_id=-100123):
    return Config(
        **{
            "bot_" + "token": "***",
            "database_url": "postgresql://prananew:***@127.0.0.1:5432/prananew",
            "admin_chat_id": admin_chat_id,
        }
    )


class FakeDatabase:
    def __init__(self):
        self.calls = []
        self.fetch_result = []
        self.fetchrow_result = {"id": 1}

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE 1"

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.fetch_result

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_result


class AdminSlotManagementTest(unittest.IsolatedAsyncioTestCase):
    def test_task_071_i18n_contains_admin_slot_keys(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("admin_generate_slots_help", language))
            self.assertTrue(t("admin_booked_slots_help", language))
            self.assertTrue(t("admin_slots_generated", language, count=3))
            self.assertTrue(t("admin_slots_report_empty", language, slot_date="2026-05-08"))
            self.assertTrue(t("admin_slot_updated", language))
            self.assertTrue(t("admin_slot_command_error", language))

    def test_task_071_generate_slots_includes_end_time_and_uses_step(self):
        specs = generate_slot_specs(
            slot_date=date(2026, 5, 8),
            step_minutes=10,
            start_at=time(14, 0),
            end_at=time(14, 30),
            capacity=2,
            tz_name="Europe/Belgrade",
        )

        self.assertEqual([time(14, 0), time(14, 10), time(14, 20), time(14, 30)], [spec.starts_at for spec in specs])
        self.assertEqual([2, 2, 2, 2], [spec.capacity for spec in specs])
        self.assertEqual(datetime(2026, 5, 8, 14, 0, tzinfo=ZoneInfo("Europe/Belgrade")), specs[0].start_time)

    def test_task_071_generate_slots_rejects_invalid_period_or_step(self):
        with self.assertRaisesRegex(AdminSlotError, "invalid_step"):
            generate_slot_specs(date(2026, 5, 8), 0, time(14, 0), time(15, 0), 1, "Europe/Belgrade")
        with self.assertRaisesRegex(AdminSlotError, "invalid_period"):
            generate_slot_specs(date(2026, 5, 8), 10, time(15, 0), time(14, 0), 1, "Europe/Belgrade")
        with self.assertRaisesRegex(AdminSlotError, "invalid_capacity"):
            generate_slot_specs(date(2026, 5, 8), 10, time(14, 0), time(15, 0), 0, "Europe/Belgrade")

    def test_task_071_parses_admin_slot_commands(self):
        parsed = parse_generate_slots_command("/generate 2026-05-08 10 14:00 14:30 2")
        self.assertEqual((date(2026, 5, 8), 10, time(14, 0), time(14, 30), 2), parsed)
        self.assertEqual(date(2026, 5, 8), parse_list_slots_command("/admin_slots 2026-05-08"))
        self.assertEqual(12, parse_block_slot_command("/block_slot 12"))
        self.assertEqual((12, 3), parse_capacity_command("/set_capacity 12 3"))

    async def test_task_071_repository_lists_all_slots_with_occupancy_and_updates_slots(self):
        db = FakeDatabase()
        db.fetch_result = [{"id": 10, "booked_count": 1, "capacity": 2, "is_blocked": False}]
        repository = SlotsRepository(db)

        slots = await repository.list_by_date_with_occupancy(date(2026, 5, 8))
        await repository.set_blocked(slot_id=10, is_blocked=True)
        await repository.set_capacity(slot_id=10, capacity=3)

        self.assertEqual(db.fetch_result, slots)
        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("LEFT JOIN booking_slots", queries)
        self.assertIn("b.status IN ('active', 'completed')", queries)
        self.assertIn("s.slot_date = $1", queries)
        self.assertIn("UPDATE slots", queries)
        self.assertIn("is_blocked = $2", queries)
        self.assertIn("UPDATE slots s", queries)
        self.assertIn("capacity = $2", queries)
        self.assertIn("$2 >= (", queries)
        self.assertIn("JOIN bookings", queries)
        self.assertIn("RETURNING", queries)

    async def test_task_071_repository_rejects_missing_slot_or_capacity_below_occupancy(self):
        db = FakeDatabase()
        db.fetchrow_result = None
        repository = SlotsRepository(db)

        self.assertFalse(await repository.set_blocked(slot_id=999, is_blocked=True))
        self.assertFalse(await repository.set_capacity(slot_id=10, capacity=1))

        queries = "\n".join(call[1] for call in db.calls)
        self.assertIn("RETURNING id", queries)
        self.assertIn("active", queries)
        self.assertIn("completed", queries)

    async def test_task_071_handlers_answer_error_when_slot_update_is_rejected(self):
        db = FakeDatabase()
        db.fetchrow_result = None
        config = make_config()
        block_message = FakeMessage(text="/block_slot 999")
        capacity_message = FakeMessage(text="/set_capacity 10 1")

        await handle_admin_slot_block(block_message, db_pool=db, config=config)
        await handle_admin_slot_capacity(capacity_message, db_pool=db, config=config)

        self.assertEqual(t("admin_slot_command_error", "ru"), block_message.answers[0][0])
        self.assertEqual(t("admin_slot_command_error", "ru"), capacity_message.answers[0][0])

    def test_task_071_report_shows_free_booked_completed_and_blocked_slots(self):
        rows = [
            {"id": 1, "starts_at": time(14, 0), "capacity": 2, "booked_count": 0, "completed_count": 0, "is_blocked": False},
            {"id": 2, "starts_at": time(14, 10), "capacity": 2, "booked_count": 1, "completed_count": 0, "is_blocked": False},
            {"id": 3, "starts_at": time(14, 20), "capacity": 1, "booked_count": 1, "completed_count": 1, "is_blocked": False},
            {"id": 4, "starts_at": time(14, 30), "capacity": 1, "booked_count": 0, "completed_count": 0, "is_blocked": True},
        ]

        text = format_admin_slots_report(date(2026, 5, 8), rows, language="ru")

        self.assertIn("14:00 свободно 0/2", text)
        self.assertIn("14:10 занято 1/2", text)
        self.assertIn("14:20 выдано 1/1 ✅", text)
        self.assertIn("14:30 заблокировано", text)

    async def test_task_071_generate_handler_creates_slots_only_for_admin_chat(self):
        db = FakeDatabase()
        admin = FakeMessage(text="/generate 2026-05-08 10 14:00 14:20 2")
        stranger = FakeMessage(chat_id=42, text="/generate 2026-05-08 10 14:00 14:20 2")

        await handle_admin_slot_generate(admin, db_pool=db, config=make_config())
        await handle_admin_slot_generate(stranger, db_pool=db, config=make_config())

        self.assertEqual(t("admin_slots_generated", "ru", count=3), admin.answers[0][0])
        self.assertEqual(t("admin_only", "ru"), stranger.answers[0][0])
        self.assertEqual(3, sum(1 for call in db.calls if call[0] == "fetchrow"))

    async def test_task_071_list_and_update_handlers_require_admin_chat(self):
        db = FakeDatabase()
        db.fetch_result = [{"id": 1, "starts_at": time(14, 0), "capacity": 1, "booked_count": 0, "completed_count": 0, "is_blocked": False}]
        config = make_config()
        messages = [
            FakeMessage(text="/admin_slots 2026-05-08"),
            FakeMessage(text="/block_slot 1"),
            FakeMessage(text="/unblock_slot 1"),
            FakeMessage(text="/set_capacity 1 2"),
        ]

        await handle_admin_slot_list(messages[0], db_pool=db, config=config)
        await handle_admin_slot_block(messages[1], db_pool=db, config=config)
        await handle_admin_slot_unblock(messages[2], db_pool=db, config=config)
        await handle_admin_slot_capacity(messages[3], db_pool=db, config=config)

        self.assertIn("14:00 свободно 0/1", messages[0].answers[0][0])
        self.assertEqual(t("admin_slot_updated", "ru"), messages[1].answers[0][0])
        self.assertEqual(t("admin_slot_updated", "ru"), messages[2].answers[0][0])
        self.assertEqual(t("admin_slot_updated", "ru"), messages[3].answers[0][0])

    async def test_task_071_admin_menu_buttons_show_command_help_with_persistent_keyboard(self):
        generate_message = FakeMessage(text=t("admin_menu_generate_slots", "ru"))
        booked_message = FakeMessage(text=t("admin_menu_booked_slots", "ru"))

        await handle_admin_generate_slots_menu(generate_message, config=make_config())
        await handle_admin_booked_slots_menu(booked_message, config=make_config())

        self.assertEqual(t("admin_generate_slots_help", "ru"), generate_message.answers[0][0])
        self.assertIsInstance(generate_message.answers[0][1]["reply_markup"], ReplyKeyboardMarkup)
        self.assertIn(t("admin_booked_slots_help", "ru"), booked_message.answers[0][0])
        self.assertIn(t("admin_bookings_help", "ru"), booked_message.answers[0][0])
        self.assertIsInstance(booked_message.answers[0][1]["reply_markup"], ReplyKeyboardMarkup)


if __name__ == "__main__":
    unittest.main()
