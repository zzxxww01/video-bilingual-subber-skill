#!/usr/bin/env python3
"""Check runtime dependencies for video-bilingual-subber."""

from __future__ import annotations

import argparse
import importlib.util
import platform
import shutil
import sys
from pathlib import Path

from common import configure_stdio_utf8, get_api_key, resolve_ffmpeg, resolve_ffprobe, run_subprocess


def has_ass_filter(ffmpeg_path: str) -> bool:
    proc = run_subprocess([ffmpeg_path, "-hide_banner", "-filters"], check=False)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    lowered = text.lower()
    return " ass " in lowered or " subtitles " in lowered


def check_python() -> tuple[bool, str]:
    ok = sys.version_info >= (3, 10)
    return ok, f"Python {platform.python_version()}"


def check_api_key() -> tuple[bool, str]:
    try:
        get_api_key(None)
    except Exception:
        return False, "GEMINI_API_KEY is missing (env/.env)"
    return True, "GEMINI_API_KEY is set (value hidden)"


def check_ffmpeg(explicit_ffmpeg: str | None) -> tuple[bool, str, str | None]:
    try:
        ffmpeg_path = resolve_ffmpeg(explicit_ffmpeg)
        version = run_subprocess([ffmpeg_path, "-version"], check=False).stdout.splitlines()[0]
        return True, f"ffmpeg found: {version}", ffmpeg_path
    except Exception as exc:  # noqa: BLE001
        return False, f"ffmpeg missing: {exc}", None


def check_ffprobe(ffmpeg_path: str | None) -> tuple[bool, str]:
    if not ffmpeg_path:
        return False, "ffprobe skipped (ffmpeg missing)"
    ffprobe = resolve_ffprobe(ffmpeg_path)
    if not ffprobe:
        return True, "ffprobe missing (optional)"
    proc = run_subprocess([ffprobe, "-version"], check=False)
    first_line = (proc.stdout or proc.stderr).splitlines()[0]
    return True, f"ffprobe found: {first_line}"


def check_youtube_downloader() -> tuple[bool, str]:
    if importlib.util.find_spec("yt_dlp") is not None:
        return True, "yt_dlp Python module is available"
    yt_dlp_cli = shutil.which("yt-dlp")
    if yt_dlp_cli:
        return True, f"yt-dlp CLI found: {yt_dlp_cli}"
    return False, "yt-dlp is missing. Install it with `pip install -r requirements.txt`."


def main() -> int:
    configure_stdio_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", help="Explicit ffmpeg binary path")
    parser.add_argument("--need-youtube", action="store_true", help="Check yt-dlp availability for YouTube downloads")
    parser.add_argument("--skip-api-key", action="store_true", help="Skip GEMINI_API_KEY check")
    parser.add_argument("--skip-ffmpeg", action="store_true", help="Skip ffmpeg/ffprobe checks")
    parser.add_argument("--skip-ass-filter", action="store_true", help="Skip ffmpeg ASS filter check")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero if any checks fail",
    )
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []

    py_ok, py_msg = check_python()
    checks.append(("python", py_ok, py_msg))

    if args.need_youtube:
        youtube_ok, youtube_msg = check_youtube_downloader()
        checks.append(("yt_dlp", youtube_ok, youtube_msg))

    if args.skip_api_key:
        key_ok, key_msg = True, "GEMINI_API_KEY check skipped"
    else:
        key_ok, key_msg = check_api_key()
    checks.append(("gemini_api_key", key_ok, key_msg))

    if args.skip_ffmpeg:
        ffmpeg_ok, ffmpeg_msg, ffmpeg_path = True, "ffmpeg check skipped", None
    else:
        ffmpeg_ok, ffmpeg_msg, ffmpeg_path = check_ffmpeg(args.ffmpeg)
    checks.append(("ffmpeg", ffmpeg_ok, ffmpeg_msg))

    if args.skip_ffmpeg:
        ffprobe_ok, ffprobe_msg = True, "ffprobe check skipped"
    else:
        ffprobe_ok, ffprobe_msg = check_ffprobe(ffmpeg_path)
    checks.append(("ffprobe", ffprobe_ok, ffprobe_msg))

    if not args.skip_ffmpeg and not args.skip_ass_filter and ffmpeg_ok and ffmpeg_path:
        ass_ok = has_ass_filter(ffmpeg_path)
        checks.append(
            (
                "ass_filter",
                ass_ok,
                "ffmpeg supports ASS/subtitles filters" if ass_ok else "ffmpeg missing ASS/subtitles filters",
            )
        )

    base_dir = Path.cwd()
    checks.append(("workspace", True, f"cwd={base_dir}"))

    print("Environment check:")
    has_failure = False
    for name, ok, msg in checks:
        status = "OK" if ok else "FAIL"
        print(f"- [{status}] {name}: {msg}")
        if not ok:
            has_failure = True

    if args.strict and has_failure:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
