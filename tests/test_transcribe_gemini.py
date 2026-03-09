import io
import sys
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import transcribe_gemini


class TranscribeCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(__file__).resolve().parents[1] / ".tmp_test_workspace" / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.input_path = self.temp_dir / "clip.mp4"
        self.output_path = self.temp_dir / "clip.en.raw.srt"
        self.input_path.write_bytes(b"fake-video")

    def tearDown(self) -> None:
        if self.temp_dir.exists():
            for path in sorted(self.temp_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()

    def _apply_common_patches(self, stack: ExitStack, argv: list[str]) -> patch:
        stack.enter_context(patch.object(sys, "argv", argv))
        stack.enter_context(patch.object(transcribe_gemini, "get_api_key", return_value="secret"))
        stack.enter_context(patch.object(transcribe_gemini, "retry", side_effect=lambda operation, **kwargs: operation()))
        stack.enter_context(patch.object(transcribe_gemini, "upload_file", return_value={"name": "files/abc123", "uri": "gs://fake"}))
        stack.enter_context(patch.object(transcribe_gemini, "wait_for_file_active", return_value={"mimeType": "video/mp4"}))
        stack.enter_context(patch.object(transcribe_gemini, "generate_content", side_effect=RuntimeError("boom")))
        delete_mock = stack.enter_context(patch.object(transcribe_gemini, "delete_file"))
        return delete_mock

    def test_cleanup_runs_when_transcription_request_fails(self) -> None:
        with ExitStack() as stack:
            delete_mock = self._apply_common_patches(
                stack,
                ["transcribe_gemini.py", "--in", str(self.input_path), "--out", str(self.output_path)],
            )
            stack.enter_context(patch("sys.stdout", io.StringIO()))
            with self.assertRaises(RuntimeError):
                transcribe_gemini.main()
        delete_mock.assert_called_once_with("secret", "files/abc123")

    def test_keep_upload_skips_cleanup_on_failure(self) -> None:
        with ExitStack() as stack:
            delete_mock = self._apply_common_patches(
                stack,
                ["transcribe_gemini.py", "--in", str(self.input_path), "--out", str(self.output_path), "--keep-upload"],
            )
            with self.assertRaises(RuntimeError):
                transcribe_gemini.main()
        delete_mock.assert_not_called()
