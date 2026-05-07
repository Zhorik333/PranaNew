import importlib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectStructureTest(unittest.TestCase):
    def test_task_001_project_structure_exists(self):
        expected_paths = [
            "bot/__init__.py",
            "bot/main.py",
            "bot/config.py",
            "bot/db.py",
            "bot/app_context.py",
            "bot/routers/__init__.py",
            "bot/keyboards/__init__.py",
            "bot/repositories/__init__.py",
            "bot/services/__init__.py",
            "bot/i18n/__init__.py",
            "bot/states/__init__.py",
            "migrations/.gitkeep",
            "tests/__init__.py",
            "README.md",
            ".env.example",
            ".gitignore",
            "requirements.txt",
        ]

        missing = [path for path in expected_paths if not (PROJECT_ROOT / path).exists()]

        self.assertEqual([], missing)

    def test_task_001_core_modules_are_importable(self):
        for module_name in ["bot.app_context", "bot.config", "bot.db", "bot.main"]:
            with self.subTest(module_name=module_name):
                importlib.import_module(module_name)


if __name__ == "__main__":
    unittest.main()
