from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ENV_EXAMPLE = ROOT / ".env.example"
DATABASE_URL_WITH_RAW_PASSWORD_RE = re.compile(
    r"postgresql://"
    r"[^\s`:/]+:"
    r"(?!(?:\*{3}|\[REDACTED\])@)"
    r"[^\s`@]{6,}@"
)


class ReadmeLocalSetupTest(unittest.TestCase):
    def setUp(self):
        self.readme = README.read_text(encoding="utf-8")
        self.readme_lower = self.readme.lower()

    def test_task_120_readme_documents_required_local_setup_steps(self):
        required_phrases = [
            "как создать .env",
            "установка зависимостей",
            "создание базы данных",
            "применение миграции",
            "запуск бота",
            "admin_chat_id",
            "/chatid",
        ]

        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.readme_lower)

    def test_task_120_readme_documents_all_env_example_variables(self):
        env_keys = []
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, _value = line.partition("=")
            env_keys.append(key)

        self.assertGreater(env_keys, [])
        for key in env_keys:
            with self.subTest(key=key):
                self.assertIn(key, self.readme)

    def test_task_120_readme_uses_project_runtime_and_test_commands(self):
        expected_snippets = [
            "cd /mnt/d/PranaNew",
            "uv venv .venv",
            "uv pip install -r requirements.txt",
            ".venv/bin/python -m unittest discover -s tests -v",
            ".venv/bin/python -m bot.main",
            "psql --version",
            "psql -h 127.0.0.1 -p 5432 -U postgres -d postgres",
            "psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 -f migrations/001_init.sql",
            "migrations/001_init.sql",
        ]

        for snippet in expected_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, self.readme)

    def test_task_120_readme_does_not_contain_real_secrets(self):
        forbidden_patterns = [
            re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"),
            DATABASE_URL_WITH_RAW_PASSWORD_RE,
        ]

        for pattern in forbidden_patterns:
            with self.subTest(pattern=pattern.pattern):
                self.assertIsNone(pattern.search(self.readme))

    def test_task_120_database_url_secret_regex_allows_only_redacted_passwords(self):
        raw_url = "DATABASE_URL=postgresql://user:" + "actual-db-value" + "@127.0.0.1:5432/db"
        self.assertIsNotNone(DATABASE_URL_WITH_RAW_PASSWORD_RE.search(raw_url))
        self.assertIsNone(
            DATABASE_URL_WITH_RAW_PASSWORD_RE.search(
                "DATABASE_URL=postgresql://user:***@127.0.0.1:5432/db"
            )
        )
        self.assertIsNone(
            DATABASE_URL_WITH_RAW_PASSWORD_RE.search(
                "DATABASE_URL=postgresql://[REDACTED]:***@127.0.0.1:5432/[REDACTED]"
            )
        )

    def test_task_120_readme_does_not_lock_postgresql_to_one_workstation_path(self):
        self.assertNotIn("/home/arts9/.local/pgsql", self.readme)


if __name__ == "__main__":
    unittest.main()
