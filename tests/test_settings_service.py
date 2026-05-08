import unittest
from datetime import time

from bot.services.settings import BotSettings, SettingsService, SettingsServiceError


class FakeAcquire:
    def __init__(self, pool):
        self.pool = pool

    async def __aenter__(self):
        self.pool.connection.events.append("acquire_enter")
        return self.pool.connection

    async def __aexit__(self, exc_type, exc, tb):
        self.pool.connection.events.append("acquire_exit")
        return False


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        self.connection.events.append("acquire_called")
        return FakeAcquire(self)


class FakeConnection:
    def __init__(self, values=None):
        self.values = values or {}
        self.events = []
        self.calls = []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return self.values.get(args[0])

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        self.values[args[0]] = args[1]
        return "EXECUTE 1"


class SettingsServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_task_012_returns_safe_defaults_when_settings_are_missing(self):
        connection = FakeConnection()
        settings = await SettingsService(FakePool(connection)).get_settings()

        self.assertEqual(
            BotSettings(
                working_start_time=time(14, 0),
                working_end_time=time(19, 0),
                slot_step=10,
                max_consecutive=5,
                tz="Europe/Belgrade",
                review_delay_minutes=30,
            ),
            settings,
        )
        self.assertIn("acquire_enter", connection.events)
        requested_keys = [call[2][0] for call in connection.calls if call[0] == "fetchval"]
        self.assertEqual(
            [
                "working_start_time",
                "working_end_time",
                "slot_step",
                "max_consecutive",
                "tz",
                "review_delay_minutes",
            ],
            requested_keys,
        )

    async def test_task_012_reads_and_validates_saved_settings(self):
        connection = FakeConnection(
            {
                "working_start_time": "10:30",
                "working_end_time": "22:00",
                "slot_step": "15",
                "max_consecutive": "4",
                "tz": "Europe/Podgorica",
                "review_delay_minutes": "45",
            }
        )

        settings = await SettingsService(FakePool(connection)).get_settings()

        self.assertEqual(time(10, 30), settings.working_start_time)
        self.assertEqual(time(22, 0), settings.working_end_time)
        self.assertEqual(15, settings.slot_step)
        self.assertEqual(4, settings.max_consecutive)
        self.assertEqual("Europe/Podgorica", settings.tz)
        self.assertEqual(45, settings.review_delay_minutes)

    async def test_task_012_rejects_invalid_stored_values(self):
        invalid_cases = [
            {"working_start_time": "bad"},
            {"working_start_time": ""},
            {"working_start_time": "10:00:30"},
            {"working_start_time": "10:00+01:00"},
            {"working_start_time": "20:00", "working_end_time": "10:00"},
            {"working_start_time": "10:00", "working_end_time": "10:00"},
            {"slot_step": ""},
            {"slot_step": "0"},
            {"slot_step": "+10"},
            {"slot_step": "١٠"},
            {"slot_step": "abc"},
            {"max_consecutive": "0"},
            {"review_delay_minutes": "-1"},
            {"tz": ""},
        ]
        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(SettingsServiceError):
                    await SettingsService(FakePool(FakeConnection(values))).get_settings()

    async def test_task_012_set_setting_validates_before_saving(self):
        connection = FakeConnection()
        service = SettingsService(FakePool(connection))

        await service.set_setting("slot_step", "20")
        await service.set_setting("working_start_time", "09:00")
        await service.set_setting("tz", "Europe/Belgrade")

        self.assertEqual("20", connection.values["slot_step"])
        self.assertEqual("09:00", connection.values["working_start_time"])
        self.assertEqual("Europe/Belgrade", connection.values["tz"])
        with self.assertRaises(SettingsServiceError):
            await service.set_setting("slot_step", "0")
        with self.assertRaises(SettingsServiceError):
            await service.set_setting("slot_step", "   ")
        with self.assertRaises(SettingsServiceError):
            await service.set_setting("working_start_time", "09:00:30")
        with self.assertRaises(SettingsServiceError):
            await service.set_setting("unknown", "value")

    async def test_task_012_set_setting_rejects_invalid_resulting_working_hours(self):
        connection = FakeConnection({"working_start_time": "10:00", "working_end_time": "19:00"})
        service = SettingsService(FakePool(connection))

        with self.assertRaises(SettingsServiceError):
            await service.set_setting("working_start_time", "20:00")
        with self.assertRaises(SettingsServiceError):
            await service.set_setting("working_start_time", "19:00")

        self.assertEqual("10:00", connection.values["working_start_time"])


if __name__ == "__main__":
    unittest.main()
