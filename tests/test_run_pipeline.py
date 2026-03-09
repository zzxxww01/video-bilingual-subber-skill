import json
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
        self.command_args: list[list[str]] = []

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)
        parent = self.temp_dir.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def fake_run(self, cmd: list[str], cwd: Path) -> None:
        script_name = Path(cmd[1]).name if len(cmd) > 1 else cmd[0]
        self.commands.append(script_name)
        self.command_args.append(list(cmd))

        if script_name == "check_env.py":
            return

        if script_name == "download_youtube.py":
            url = cmd[cmd.index("--url") + 1]
            captions_mode = cmd[cmd.index("--captions-mode") + 1]
            if "fail" in url:
                raise RuntimeError("download failed")
            video_id = url.split("v=")[-1]
            download_dir = Path(cmd[cmd.index("--download-dir") + 1])
            out_meta = Path(cmd[cmd.index("--out-meta") + 1])
            stem = f"Example {video_id} [{video_id}]"
            video_path = download_dir / f"{stem}.mp4"
            download_dir.mkdir(parents=True, exist_ok=True)
            video_path.write_bytes(b"downloaded-video")

            caption_path = None
            caption_source = "none"
            if captions_mode != "off" and "nocap" not in url:
                caption_path = download_dir / f"{stem}.en.raw.srt"
                caption_path.write_text(EN_SRT, encoding="utf-8-sig")
                caption_source = "youtube_caption"

            out_meta.parent.mkdir(parents=True, exist_ok=True)
            out_meta.write_text(
                json.dumps(
                    {
                        "source_type": "youtube",
                        "source_url": url,
                        "video_id": video_id,
                        "title": f"Example {video_id}",
                        "downloaded_video_path": str(video_path),
                        "english_caption_path": str(caption_path) if caption_path else None,
                        "caption_source": caption_source,
                        "download_dir": str(download_dir),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
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
            rc = self.invoke("clip.mp4", "--approve-burn", "--resume", "--no-copy")

        self.assertEqual(rc, 0)
        self.assertIn("burn_ass.py", self.commands)
        self.assertTrue((self.temp_dir / "final_videos" / "clip.zh-en-hard.mp4").exists())
        env_cmd = next(cmd for cmd in self.command_args if Path(cmd[1]).name == "check_env.py")
        self.assertIn("--skip-api-key", env_cmd)

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

    def test_changed_batch_size_invalidates_existing_bilingual_outputs(self) -> None:
        subs_dir = self.temp_dir / "subs"
        output_dir = self.temp_dir / "output"
        subs_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        en_srt = subs_dir / "clip.en.raw.srt"
        bi_srt = subs_dir / "clip.zh_en.srt"
        bi_ass = subs_dir / "clip.zh_en.ass"
        review_path = output_dir / "clip.subtitle-review.txt"
        manifest_path = output_dir / "clip.pipeline-manifest.json"
        en_srt.write_text(EN_SRT, encoding="utf-8-sig")
        bi_srt.write_text(BI_SRT, encoding="utf-8-sig")
        bi_ass.write_text("[Script Info]\n", encoding="utf-8")
        review_path.write_text("already reviewed", encoding="utf-8")

        video_info = run_pipeline.build_video_fingerprint(self.temp_dir / "clip.mp4")
        source_info = {
            "type": "local",
            "input": "clip.mp4",
            "video": video_info,
            "caption_source": "gemini_transcribe",
        }
        manifest = {
            "version": run_pipeline.MANIFEST_VERSION,
            "video": video_info,
            "source": source_info,
            "artifacts": {
                "en_srt": run_pipeline.artifact_record(
                    config={"model": "gemini-3-pro-preview"},
                    inputs={"video": video_info, "source": source_info},
                ),
                "bi_srt": run_pipeline.artifact_record(
                    config={
                        "model": "gemini-3-pro-preview",
                        "batch_size": 10,
                        "glossary": run_pipeline.build_glossary_fingerprint(run_pipeline.DEFAULT_GLOSSARY),
                    },
                    inputs={
                        "source": source_info,
                        "video": video_info,
                        "en_srt": run_pipeline.build_file_fingerprint(en_srt),
                    },
                ),
                "bi_ass": run_pipeline.artifact_record(
                    config={
                        "zh_size": 48,
                        "en_size": 34,
                        "zh_font": "Microsoft YaHei",
                        "en_font": "Arial",
                    },
                    inputs={
                        "source": source_info,
                        "bi_srt": run_pipeline.build_file_fingerprint(bi_srt),
                    },
                ),
            },
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("clip.mp4", "--resume")

        self.assertEqual(rc, 0)
        self.assertIn("translate_bilingual.py", self.commands)
        self.assertIn("srt_to_ass.py", self.commands)
        self.assertNotIn("burn_ass.py", self.commands)

    def test_youtube_url_uses_downloaded_captions_and_skips_transcription(self) -> None:
        url = "https://www.youtube.com/watch?v=abc123"
        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("--url", url)

        self.assertEqual(rc, 0)
        self.assertIn("download_youtube.py", self.commands)
        self.assertNotIn("transcribe_gemini.py", self.commands)
        env_cmds = [cmd for cmd in self.command_args if Path(cmd[1]).name == "check_env.py"]
        self.assertGreaterEqual(len(env_cmds), 2)
        self.assertIn("--need-youtube", env_cmds[0])
        review_path = self.temp_dir / "output" / "Example abc123 [abc123].subtitle-review.txt"
        self.assertTrue(review_path.exists())

    def test_youtube_url_without_captions_falls_back_to_transcription(self) -> None:
        url = "https://www.youtube.com/watch?v=nocap123"
        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("--url", url)

        self.assertEqual(rc, 0)
        self.assertIn("download_youtube.py", self.commands)
        self.assertIn("transcribe_gemini.py", self.commands)

    def test_no_youtube_captions_flag_forces_transcription(self) -> None:
        url = "https://www.youtube.com/watch?v=abc123"
        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("--url", url, "--no-youtube-captions")

        self.assertEqual(rc, 0)
        self.assertIn("download_youtube.py", self.commands)
        self.assertIn("transcribe_gemini.py", self.commands)

    def test_cookies_from_browser_flag_is_passed_to_download_script(self) -> None:
        url = "https://www.youtube.com/watch?v=abc123"
        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("--url", url, "--cookies-from-browser", "chrome")

        self.assertEqual(rc, 0)
        download_cmd = next(cmd for cmd in self.command_args if Path(cmd[1]).name == "download_youtube.py")
        self.assertIn("--cookies-from-browser", download_cmd)
        self.assertIn("chrome", download_cmd)

    def test_cookie_file_flag_is_passed_to_download_script(self) -> None:
        url = "https://www.youtube.com/watch?v=abc123"
        cookie_file = str(self.temp_dir / "youtube.cookies.txt")
        Path(cookie_file).write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("--url", url, "--cookies", cookie_file)

        self.assertEqual(rc, 0)
        download_cmd = next(cmd for cmd in self.command_args if Path(cmd[1]).name == "download_youtube.py")
        self.assertIn("--cookies", download_cmd)
        self.assertIn(cookie_file, download_cmd)

    def test_youtube_batch_continues_after_single_failure(self) -> None:
        fail_url = "https://www.youtube.com/watch?v=fail123"
        ok_url = "https://www.youtube.com/watch?v=ok999"
        with patch.object(run_pipeline, "run", side_effect=self.fake_run):
            rc = self.invoke("--url", fail_url, "--url", ok_url)

        self.assertEqual(rc, 1)
        self.assertGreaterEqual(self.commands.count("download_youtube.py"), 2)
        review_path = self.temp_dir / "output" / "Example ok999 [ok999].subtitle-review.txt"
        self.assertTrue(review_path.exists())


if __name__ == "__main__":
    unittest.main()
