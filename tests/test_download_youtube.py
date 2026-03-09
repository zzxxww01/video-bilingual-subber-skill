import shutil
import sys
import unittest
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import download_youtube


class DownloadYoutubeHelpersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(__file__).resolve().parents[1] / ".tmp_test_workspace" / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)
        parent = self.temp_dir.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def test_pick_best_english_lang_prefers_exact_en(self) -> None:
        lang = download_youtube.pick_best_english_lang({"en-US": {}, "en": {}, "fr": {}})
        self.assertEqual(lang, "en")

    def test_parse_cookies_from_browser_supports_plain_browser_name(self) -> None:
        parsed = download_youtube.parse_cookies_from_browser("chrome")
        self.assertEqual(parsed, ("chrome", None, None, None))

    def test_resolve_cookie_file_returns_absolute_existing_path(self) -> None:
        cookie_path = self.temp_dir / "youtube.cookies.txt"
        cookie_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

        resolved = download_youtube.resolve_cookie_file(str(cookie_path))

        self.assertEqual(resolved, cookie_path.resolve())

    def test_parse_webvtt_converts_to_srt_entries(self) -> None:
        vtt_path = self.temp_dir / "sample.vtt"
        vtt_path.write_text(
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.250\n"
            "<c.colorE5E5E5>Hello</c>\n\n"
            "cue-2\n"
            "00:00:01.250 --> 00:00:02.000 align:start\n"
            "World &amp; more\n",
            encoding="utf-8",
        )

        entries = download_youtube.parse_webvtt(vtt_path)

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].text, "Hello")
        self.assertEqual(entries[0].start_ms, 0)
        self.assertEqual(entries[0].end_ms, 1250)
        self.assertEqual(entries[1].text, "World & more")


if __name__ == "__main__":
    unittest.main()
