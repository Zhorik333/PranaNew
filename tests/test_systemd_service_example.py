from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_EXAMPLE = PROJECT_ROOT / "deploy" / "prananew-bot.service.example"


class SystemdServiceExampleTest(unittest.TestCase):
    def test_service_example_exists_in_deploy_directory(self):
        self.assertTrue(SERVICE_EXAMPLE.exists())
        self.assertTrue(SERVICE_EXAMPLE.is_file())

    def test_service_example_contains_required_systemd_sections(self):
        content = SERVICE_EXAMPLE.read_text(encoding="utf-8")

        self.assertIn("[Unit]", content)
        self.assertIn("[Service]", content)
        self.assertIn("[Install]", content)

    def test_service_example_documents_safe_runtime_command(self):
        content = SERVICE_EXAMPLE.read_text(encoding="utf-8")

        self.assertIn("WorkingDirectory=/opt/prananew", content)
        self.assertIn("EnvironmentFile=/opt/prananew/.env", content)
        self.assertIn("ExecStart=/opt/prananew/.venv/bin/python -m bot.main", content)

    def test_service_example_has_restart_policy(self):
        content = SERVICE_EXAMPLE.read_text(encoding="utf-8")

        self.assertIn("Restart=always", content)
        self.assertIn("RestartSec=5", content)

    def test_service_example_uses_generic_server_paths_without_secrets(self):
        content = SERVICE_EXAMPLE.read_text(encoding="utf-8")

        forbidden_fragments = [
            "/mnt/",
            "D:",
            "C:",
            "BOT" + "_" + "TOK" + "EN=",
            "DATABASE" + "_" + "URL=",
            "ADMIN" + "_CHAT" + "_ID=",
            "postgresql://",
        ]
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, content)


if __name__ == "__main__":
    unittest.main()
