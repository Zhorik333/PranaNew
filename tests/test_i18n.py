import unittest
from pathlib import Path

from bot.i18n import DEFAULT_LANGUAGE, REQUIRED_KEYS, SUPPORTED_LANGUAGES, normalize_language, t


class I18nMessagesTest(unittest.TestCase):
    def test_task_010_dictionary_supports_ru_en_sr_for_all_mvp_keys(self):
        self.assertEqual("ru", DEFAULT_LANGUAGE)
        self.assertEqual({"ru", "en", "sr"}, SUPPORTED_LANGUAGES)

        for language in SUPPORTED_LANGUAGES:
            for key in REQUIRED_KEYS:
                with self.subTest(language=language, key=key):
                    value = t(key, language)
                    self.assertIsInstance(value, str)
                    self.assertNotEqual("", value.strip())
                    self.assertNotEqual(key, value)

    def test_task_010_unknown_language_falls_back_to_russian(self):
        self.assertEqual(t("welcome", "ru"), t("welcome", "de"))
        self.assertEqual(t("welcome", "ru"), t("welcome", None))

    def test_task_010_telegram_language_codes_are_normalized(self):
        self.assertEqual("ru", normalize_language("ru-RU"))
        self.assertEqual("en", normalize_language("en-US"))
        self.assertEqual("sr", normalize_language("sr-Latn"))
        self.assertEqual("ru", normalize_language("de-DE"))
        self.assertEqual("ru", normalize_language(None))

    def test_task_010_messages_support_named_formatting(self):
        self.assertIn("5", t("max_consecutive_error", "en", max_slots=5))
        self.assertIn("15:30", t("pickup_time", "ru", time="15:30"))
        self.assertIn("15:30", t("pickup_time", "sr", time="15:30"))

    def test_task_010_unknown_key_raises_clear_error(self):
        with self.assertRaisesRegex(KeyError, "Unknown i18n key"):
            t("missing_key", "ru")

    def test_task_010_handlers_do_not_hardcode_user_facing_text(self):
        handler_files = [
            Path("bot/main.py"),
            *Path("bot/routers").glob("*.py"),
        ]
        forbidden_fragments = [
            "Бот PranaNew запущен",
            "Бронирование слотов будет добавлено далее",
            "Choose language",
            "No slots available",
            "Booking confirmed",
        ]

        for path in handler_files:
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, text, path.as_posix())


if __name__ == "__main__":
    unittest.main()
