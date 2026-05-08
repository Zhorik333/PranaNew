from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = PROJECT_ROOT / "docs" / "mvp_release_checklist.md"


class MvpReleaseChecklistTest(unittest.TestCase):
    def test_task_123_release_checklist_exists_in_docs(self):
        self.assertTrue(CHECKLIST.exists())
        self.assertTrue(CHECKLIST.is_file())

    def test_task_123_release_checklist_contains_required_sections(self):
        content = CHECKLIST.read_text(encoding="utf-8")

        required_headings = [
            "# MVP Release Checklist",
            "## 1. Code and backlog readiness",
            "## 2. Database and migrations",
            "## 3. Local verification",
            "## 4. Telegram smoke test",
            "## 5. Admin smoke test",
            "## 6. Client booking smoke test",
            "## 7. Security and secrets",
            "## 8. Deployment readiness",
            "## 9. Release decision",
        ]
        for heading in required_headings:
            with self.subTest(heading=heading):
                self.assertIn(heading, content)

    def test_task_123_release_checklist_covers_backlog_acceptance_criteria(self):
        content = CHECKLIST.read_text(encoding="utf-8")

        required_items = [
            "All P0 backlog tasks are completed and closed before MVP release.",
            "Apply migrations to a clean PostgreSQL database",
            ".venv/bin/python -m unittest discover -s tests -v",
            "Bot answers `/start`",
            "Admin can generate slots with `/generate DATE STEP START END [CAPACITY]`",
            "Client can book one or multiple consecutive slots",
            "Double booking is rejected or returns the existing active booking idempotently",
            "Language switching works for RU/EN/SR",
            "`.env` is not tracked by git",
        ]
        for item in required_items:
            with self.subTest(item=item):
                self.assertIn(item, content)

    def test_task_123_release_checklist_has_actionable_commands_without_real_secrets(self):
        content = CHECKLIST.read_text(encoding="utf-8")

        required_commands = [
            "git status --short --branch",
            "psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 -f migrations/001_init.sql",
            ".venv/bin/python -m compileall bot tests",
            ".venv/bin/python -m bot.main",
            "systemctl status prananew-bot",
        ]
        for command in required_commands:
            with self.subTest(command=command):
                self.assertIn(command, content)

        forbidden_fragments = [
            "BOT" + "_" + "TOK" + "EN" + chr(61),
            "DATABASE" + "_" + "URL" + chr(61),
            "ADMIN" + "_CHAT" + "_ID" + chr(61),
            "/mnt/",
            "D:",
            "C:",
        ]
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, content)

    def test_task_123_release_checklist_uses_checkbox_format(self):
        content = CHECKLIST.read_text(encoding="utf-8")

        checked_lines = [line for line in content.splitlines() if line.startswith("- [ ] ")]
        self.assertGreaterEqual(len(checked_lines), 20)


if __name__ == "__main__":
    unittest.main()
