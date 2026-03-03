#!/usr/bin/env python3
"""Check runtime dependencies for video-bilingual-subber."""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from common import get_api_key, resolve_ffmpeg, resolve_ffprobe, run_subprocess


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", help="Explicit ffmpeg binary path")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero if any checks fail",
    )
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []

    py_ok, py_msg = check_python()
    checks.append(("python", py_ok, py_msg))

    key_ok, key_msg = check_api_key()
    checks.append(("gemini_api_key", key_ok, key_msg))

    ffmpeg_ok, ffmpeg_msg, ffmpeg_path = check_ffmpeg(args.ffmpeg)
    checks.append(("ffmpeg", ffmpeg_ok, ffmpeg_msg))

    ffprobe_ok, ffprobe_msg = check_ffprobe(ffmpeg_path)
    checks.append(("ffprobe", ffprobe_ok, ffprobe_msg))

    if ffmpeg_ok and ffmpeg_path:
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
