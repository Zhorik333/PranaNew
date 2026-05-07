import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def requirement_names():
    names = set()
    for raw_line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~;\[]", line, maxsplit=1)[0].strip().lower().replace("_", "-")
        names.add(name)
    return names


class RequirementsTest(unittest.TestCase):
    def test_task_002_runtime_and_test_dependencies_are_declared(self):
        expected = {
            "aiogram",
            "asyncpg",
            "python-dotenv",
            "pytest",
        }

        self.assertLessEqual(expected, requirement_names())


if __name__ == "__main__":
    unittest.main()
