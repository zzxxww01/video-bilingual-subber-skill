import shutil
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_pipeline

EN_SRT = """1
00:00:00,000 --> 00:00:01,000
Hello
"""

BI_SRT = """1
00:00:00,000 --> 00:00:01,000
ZH line one
Hello

2
00:00:01,000 --> 00:00:02,000
ZH line two
World
"""


class RunPipelineReviewFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(__file__).resolve().parents[1] / ".tmp_test_workspace" / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "clip.mp4").write_bytes(b"fake-video")
        self.commands: list[str] = []

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)
        parent = self.temp_dir.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def fake_run(self, cmd: list[str], cwd: Path) -> None:
        script_name = Path(cmd[1]).name if len(cmd) > 1 else cmd[0]
        self.commands.append(script_name)

        if script_name == "check_env.py":
            return

        if script_name == "transcribe_gemini.py":
            out = Path(cmd[cmd.index("--out") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(EN_SRT, encoding="utf-8-sig")
            return

        if script_name == "translate_bilingual.py":
            out = Path(cmd[cmd.index("--out") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(BI_SRT, encoding="utf-8-sig")
            return

        if script_name == "srt_to_ass.py":
            out = Path(cmd[cmd.index("--out") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("[Script Info]\n", encoding="utf-8")
            return

        if script_name == "burn_ass.py":
            out = Path(cmd[cmd.index("--out") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"hard-sub-video")
            return

        if script_name == "generate_copy.py":
            out = Path(cmd[cmd.index("--out") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text('{"title":"t","description":"d","hashtags":["#x"]}', encoding="utf-8")
            return

        raise AssertionError(f"Unexpected command: {cmd}")

    def invoke(self, *argv: str) -> int:
        with patch.object(sys, "argv", ["run_pipeline.py", *argv]), patch.object(
            run_pipeline.Path, "cwd", return_value=self.temp_dir
        ):
            return run_pipeline.main()

    def test_first_run_holds_for_review_even_when_burn_is_approved(self) -> None:
        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("clip.mp4", "--approve-burn")

        self.assertEqual(rc, 0)
        self.assertTrue((self.temp_dir / "output" / "clip.subtitle-review.txt").exists())
        self.assertNotIn("burn_ass.py", self.commands)
        self.assertFalse((self.temp_dir / "final_videos" / "clip.zh-en-hard.mp4").exists())

    def test_second_run_can_burn_after_review_file_already_exists(self) -> None:
        subs_dir = self.temp_dir / "subs"
        output_dir = self.temp_dir / "output"
        subs_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        (subs_dir / "clip.en.raw.srt").write_text(EN_SRT, encoding="utf-8-sig")
        (subs_dir / "clip.zh_en.srt").write_text(BI_SRT, encoding="utf-8-sig")
        (subs_dir / "clip.zh_en.ass").write_text("[Script Info]\n", encoding="utf-8")
        (output_dir / "clip.subtitle-review.txt").write_text("already reviewed", encoding="utf-8")

        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("clip.mp4", "--approve-burn", "--resume")

        self.assertEqual(rc, 0)
        self.assertIn("burn_ass.py", self.commands)
        self.assertTrue((self.temp_dir / "final_videos" / "clip.zh-en-hard.mp4").exists())

    def test_stale_review_file_blocks_burn_until_review_is_refreshed(self) -> None:
        subs_dir = self.temp_dir / "subs"
        output_dir = self.temp_dir / "output"
        subs_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        review_path = output_dir / "clip.subtitle-review.txt"
        review_path.write_text("older review", encoding="utf-8")
        time.sleep(0.02)
        (subs_dir / "clip.en.raw.srt").write_text(EN_SRT, encoding="utf-8-sig")
        (subs_dir / "clip.zh_en.srt").write_text(BI_SRT, encoding="utf-8-sig")
        (subs_dir / "clip.zh_en.ass").write_text("[Script Info]\n", encoding="utf-8")

        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("clip.mp4", "--approve-burn", "--resume")

        self.assertEqual(rc, 0)
        self.assertNotIn("burn_ass.py", self.commands)
        self.assertFalse((self.temp_dir / "final_videos" / "clip.zh-en-hard.mp4").exists())


if __name__ == "__main__":
    unittest.main()
