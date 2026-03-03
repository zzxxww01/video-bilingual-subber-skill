#!/usr/bin/env python3
"""Burn ASS subtitles into MP4 using ffmpeg."""

from __future__ import annotations

import argparse
import shutil
import uuid
from pathlib import Path

from common import ensure_parent, resolve_ffmpeg, run_subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--ass", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ffmpeg", help="Optional explicit ffmpeg path")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--audio-bitrate", default="192k")
    parser.add_argument("--log", help="Optional ffmpeg log output file")
    args = parser.parse_args()

    video = Path(args.video).resolve()
    ass = Path(args.ass).resolve()
    out = Path(args.out).resolve()

    if not video.exists():
        raise FileNotFoundError(video)
    if not ass.exists():
        raise FileNotFoundError(ass)

    ffmpeg = resolve_ffmpeg(args.ffmpeg)
    ensure_parent(out)

    logs_dir = out.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log).resolve() if args.log else logs_dir / f"{out.stem}.ffmpeg.log"

    temp_root = out.parent / ".tmp_burn"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / f"run_{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    safe_ass = temp_dir / "subtitle.ass"
    safe_out = temp_dir / "render.mp4"

    try:
        shutil.copy2(ass, safe_ass)

        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-vf",
            f"ass={safe_ass.name}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            args.preset,
            "-crf",
            str(args.crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            args.audio_bitrate,
            str(safe_out),
        ]
        print(f"[info] burning subtitles with ffmpeg: {ffmpeg}")
        proc = run_subprocess(cmd, cwd=temp_dir, check=False)
        log_path.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed with code {proc.returncode}. Check log: {log_path}"
            )
        shutil.move(str(safe_out), str(out))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"[done] wrote hard-subtitled video -> {out}")
    print(f"[info] ffmpeg log -> {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
