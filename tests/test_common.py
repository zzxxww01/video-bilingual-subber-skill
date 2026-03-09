import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common


class CommonDotenvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(__file__).resolve().parents[1] / ".tmp_test_workspace" / uuid.uuid4().hex
        self.child_dir = self.temp_root / "nested" / "skill"
        self.child_dir.mkdir(parents=True, exist_ok=True)
        self.dotenv_path = self.temp_root / ".env"
        self.dotenv_path.write_text(
            "GEMINI_API_KEY=test-key\n"
            "YTDLP_COOKIE_FILE=secrets/youtube.cookies.txt\n",
            encoding="utf-8",
        )
        cookie_path = self.temp_root / "secrets" / "youtube.cookies.txt"
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookie_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        self.previous_loaded = common._ENV_LOADED
        self.old_env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        common._ENV_LOADED = self.previous_loaded
        shutil.rmtree(self.temp_root)
        parent = self.temp_root.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def test_load_dotenv_searches_parent_directories(self) -> None:
        common._ENV_LOADED = False
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("YTDLP_COOKIE_FILE", None)

        with patch.object(common.Path, "cwd", return_value=self.child_dir):
            common.load_dotenv_if_present()
            cookie_path = common.get_optional_path_env("YTDLP_COOKIE_FILE")

        self.assertEqual(os.environ.get("GEMINI_API_KEY"), "test-key")
        self.assertEqual(cookie_path, (self.temp_root / "secrets" / "youtube.cookies.txt").resolve())


if __name__ == "__main__":
    unittest.main()
