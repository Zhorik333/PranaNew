import os
import tempfile
import unittest
from pathlib import Path

from bot.config import ConfigError, load_config


class ConfigTest(unittest.TestCase):
    def test_task_003_loads_required_and_default_settings_from_env_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "BOT_TOKEN=123456:ABCDEF\n"
                "DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/prananew\n"
                "ADMIN_CHAT_ID=-1001234567890\n",
                encoding="utf-8",
            )

            config = load_config(env_path)

        self.assertEqual("123456:ABCDEF", config.bot_token)
        self.assertEqual("postgresql://user:pass@127.0.0.1:5432/prananew", config.database_url)
        self.assertEqual(-1001234567890, config.admin_chat_id)
        self.assertEqual("ru", config.default_language)
        self.assertEqual("Europe/Belgrade", config.default_tz)
        self.assertEqual(30, config.review_delay_minutes)
        self.assertEqual("INFO", config.log_level)

    def test_task_003_missing_required_setting_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "BOT_TOKEN=123456:ABCDEF\n"
                "ADMIN_CHAT_ID=-1001234567890\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "DATABASE_URL"):
                load_config(env_path)

    def test_task_003_environment_values_override_env_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "BOT_TOKEN=file-token\n"
                "DATABASE_URL=postgresql://file:pass@127.0.0.1:5432/prananew\n"
                "ADMIN_CHAT_ID=-100\n",
                encoding="utf-8",
            )

            old_value = os.environ.get("BOT_TOKEN")
            os.environ["BOT_TOKEN"] = "environment-token"
            try:
                config = load_config(env_path)
            finally:
                if old_value is None:
                    os.environ.pop("BOT_TOKEN", None)
                else:
                    os.environ["BOT_TOKEN"] = old_value

        self.assertEqual("environment-token", config.bot_token)

    def test_task_003_config_repr_does_not_expose_bot_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "BOT_TOKEN=secret-token-value\n"
                "DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/prananew\n"
                "ADMIN_CHAT_ID=-1001234567890\n",
                encoding="utf-8",
            )

            config = load_config(env_path)

        self.assertNotIn("secret-token-value", repr(config))

    def test_task_003_invalid_integer_setting_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "BOT_TOKEN=123456:ABCDEF\n"
                "DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/prananew\n"
                "ADMIN_CHAT_ID=not-an-int\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "ADMIN_CHAT_ID"):
                load_config(env_path)


if __name__ == "__main__":
    unittest.main()
