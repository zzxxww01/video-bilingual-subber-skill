#!/usr/bin/env python3
"""Run end-to-end bilingual subtitle + copy generation pipeline."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Sequence

from common import format_command, parse_srt

SCRIPT_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_ROOT.parent
DEFAULT_GLOSSARY = SKILL_ROOT / "references" / "glossary.sample.json"


def run(cmd: Sequence[str], cwd: Path) -> None:
    print(f"[run] {format_command(list(cmd))}", flush=True)
    proc = subprocess.run(cmd, cwd=str(cwd), check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {format_command(list(cmd))}")


def pick_video(video_arg: str | None, video_option: str | None, cwd: Path) -> Path:
    raw = video_arg or video_option
    if not raw:
        raise RuntimeError("Missing video input. Provide <video> positional arg or --video.")

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    if candidate.exists():
        return candidate.resolve()

    # If extension omitted, prefer common video suffixes.
    stem = Path(raw).stem if Path(raw).suffix else raw
    suffixes = [".mp4", ".mov", ".mkv", ".m4v", ".webm"]
    for suffix in suffixes:
        maybe = cwd / f"{stem}{suffix}"
        if maybe.exists():
            return maybe.resolve()

    matches = list(cwd.glob(f"{stem}.*"))
    video_matches = [m for m in matches if m.suffix.lower() in suffixes]
    if len(video_matches) == 1:
        return video_matches[0].resolve()
    if len(video_matches) > 1:
        names = ", ".join(m.name for m in video_matches)
        raise RuntimeError(f"Multiple videos matched '{raw}': {names}. Please specify exact file.")

    raise FileNotFoundError(f"Video not found: {raw}")


def exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def write_review_file(srt_path: Path, review_path: Path, review_lines: int) -> tuple[int, str]:
    entries = parse_srt(srt_path)
    if not entries:
        raise RuntimeError(f"No subtitle entries for review: {srt_path}")

    review_path.parent.mkdir(parents=True, exist_ok=True)
    preview_count = max(1, review_lines)
    sample = entries[:preview_count]
    lines: list[str] = []
    lines.append(f"Subtitle review for: {srt_path.name}")
    lines.append(f"Total entries: {len(entries)}")
    lines.append("Review status: pending manual check")
    lines.append("Next step: inspect this file, then rerun with --approve-burn --resume.")
    lines.append("")
    lines.append("Sample:")
    lines.append("")
    for entry in sample:
        text_lines = entry.text.splitlines()
        zh = text_lines[0] if text_lines else ""
        en = " ".join(text_lines[1:]).strip() if len(text_lines) > 1 else ""
        lines.append(f"[{entry.index}] {entry.start_ms}ms -> {entry.end_ms}ms")
        lines.append(f"ZH: {zh}")
        lines.append(f"EN: {en}")
        lines.append("")
    review_path.write_text("\n".join(lines), encoding="utf-8-sig")
    first_zh = sample[0].text.splitlines()[0] if sample and sample[0].text.splitlines() else ""
    return len(entries), first_zh


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-command bilingual subtitle pipeline. Chinese is larger and appears above English."
    )
    parser.add_argument("video", nargs="?", help="Local video file path (recommended positional input)")
    parser.add_argument("--video", dest="video_option", help="Local video file path")
    parser.add_argument("--model", default="gemini-3-pro-preview")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--zh-size", type=int, default=48)
    parser.add_argument("--en-size", type=int, default=34)
    parser.add_argument("--glossary", help="Optional glossary JSON path")
    parser.add_argument("--no-glossary", action="store_true", help="Disable default glossary")
    parser.add_argument("--copy", action="store_true", help="Generate title/description/hashtags JSON")
    parser.add_argument("--no-copy", action="store_true", help="Skip copy generation")
    parser.add_argument("--resume", action="store_true", help="Skip completed steps if outputs already exist")
    parser.add_argument("--force", action="store_true", help="Re-run all steps even if outputs exist")
    parser.add_argument("--approve-burn", action="store_true", help="Required to burn hard subtitles into video")
    parser.add_argument("--review-lines", type=int, default=12, help="How many subtitle entries to include in review file")
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be > 0")
    if args.review_lines <= 0:
        raise ValueError("--review-lines must be > 0")

    root = Path.cwd()
    video = pick_video(args.video, args.video_option, root)
    subs_dir = root / "subs"
    output_dir = root / "output"
    final_videos_dir = root / "final_videos"
    logs_dir = output_dir / "logs"
    subs_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_videos_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    stem = video.stem
    en_srt = subs_dir / f"{stem}.en.raw.srt"
    bi_srt = subs_dir / f"{stem}.zh_en.srt"
    bi_ass = subs_dir / f"{stem}.zh_en.ass"
    out_mp4 = final_videos_dir / f"{stem}.zh-en-hard.mp4"
    out_log = logs_dir / f"{stem}.zh-en-hard.ffmpeg.log"
    out_copy = output_dir / f"{stem}.copy.json"
    review_txt = output_dir / f"{stem}.subtitle-review.txt"
    had_review_file = exists_nonempty(review_txt)
    review_is_stale = True
    if had_review_file:
        review_mtime = review_txt.stat().st_mtime
        review_is_stale = any(
            exists_nonempty(path) and review_mtime < path.stat().st_mtime
            for path in (bi_srt, bi_ass)
        )

    do_copy = True
    if args.copy:
        do_copy = True
    if args.no_copy:
        do_copy = False

    resume = args.resume or (not args.force)
    glossary_path: Path | None = None
    if not args.no_glossary:
        if args.glossary:
            glossary_path = Path(args.glossary).resolve()
        elif DEFAULT_GLOSSARY.exists():
            glossary_path = DEFAULT_GLOSSARY

    review_required = (not had_review_file) or review_is_stale

    # Ensure this process inherits no stale PYTHONDONTWRITEBYTECODE choice from previous runs.
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    run(["python", str(SCRIPT_ROOT / "check_env.py"), "--strict"], cwd=root)

    if not (resume and exists_nonempty(en_srt)):
        run(
            [
                "python",
                str(SCRIPT_ROOT / "transcribe_gemini.py"),
                "--in",
                str(video),
                "--out",
                str(en_srt),
                "--model",
                args.model,
            ],
            cwd=root,
        )
        review_required = True
    else:
        print(f"[skip] transcription exists: {en_srt}")

    if not (resume and exists_nonempty(bi_srt)):
        translate_cmd = [
            "python",
            str(SCRIPT_ROOT / "translate_bilingual.py"),
            "--in",
            str(en_srt),
            "--out",
            str(bi_srt),
            "--model",
            args.model,
            "--batch-size",
            str(args.batch_size),
        ]
        if glossary_path:
            translate_cmd.extend(["--glossary", str(glossary_path)])
        run(translate_cmd, cwd=root)
        review_required = True
    else:
        print(f"[skip] bilingual srt exists: {bi_srt}")

    if not (resume and exists_nonempty(bi_ass)):
        run(
            [
                "python",
                str(SCRIPT_ROOT / "srt_to_ass.py"),
                "--in",
                str(bi_srt),
                "--out",
                str(bi_ass),
                "--zh-size",
                str(args.zh_size),
                "--en-size",
                str(args.en_size),
            ],
            cwd=root,
        )
        review_required = True
    else:
        print(f"[skip] ass exists: {bi_ass}")

    total_entries, first_zh = write_review_file(bi_srt, review_txt, args.review_lines)
    print(f"[review] subtitle file ready: {bi_srt}")
    print(f"[review] subtitle sample file: {review_txt}")
    print(f"[review] total entries: {total_entries}")
    print(f"[review] first zh line: {first_zh}")

    next_cmd = (
        f"python {SCRIPT_ROOT / 'run_pipeline.py'} "
        f"\"{video}\" --approve-burn --resume"
    )

    if review_required:
        print("[hold] Review required because subtitle outputs were created or updated in this run.")
        print(f"[action] Open the review sample and check translations before burning: {review_txt}")
        print(f"[next] After review, rerun: {next_cmd}")
        return 0

    if not args.approve_burn:
        print("[hold] Burn step is blocked until you confirm subtitles.")
        print(f"[action] Open the review sample and check translations before burning: {review_txt}")
        print(f"[next] After confirmation, run: {next_cmd}")
        return 0

    if not (resume and exists_nonempty(out_mp4)):
        run(
            [
                "python",
                str(SCRIPT_ROOT / "burn_ass.py"),
                "--video",
                str(video),
                "--ass",
                str(bi_ass),
                "--out",
                str(out_mp4),
                "--log",
                str(out_log),
            ],
            cwd=root,
        )
    else:
        print(f"[skip] hard-sub video exists: {out_mp4}")

    if do_copy:
        if not (resume and exists_nonempty(out_copy)):
            run(
                [
                    "python",
                    str(SCRIPT_ROOT / "generate_copy.py"),
                    "--video",
                    str(video),
                    "--srt",
                    str(bi_srt),
                    "--model",
                    args.model,
                    "--out",
                    str(out_copy),
                ],
                cwd=root,
            )
        else:
            print(f"[skip] copy exists: {out_copy}")

    print("[done] pipeline completed.")
    print(f"[done] hard subtitle video: {out_mp4}")
    if do_copy:
        print(f"[done] copy package: {out_copy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
