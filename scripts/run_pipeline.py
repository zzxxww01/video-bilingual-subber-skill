#!/usr/bin/env python3
"""Run end-to-end bilingual subtitle + copy generation pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from common import configure_stdio_utf8, format_command, get_default_model, parse_srt

SCRIPT_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_ROOT.parent
DEFAULT_GLOSSARY = SKILL_ROOT / "references" / "glossary.sample.json"
DEFAULT_DOWNLOAD_DIR = "downloads"
MANIFEST_VERSION = 2
VIDEO_SUFFIXES = [".mp4", ".mov", ".mkv", ".m4v", ".webm"]
_SHA256_SIZE_LIMIT = 100 * 1024 * 1024  # skip SHA256 for files > 100 MB


@dataclass
class ResolvedSource:
    source_type: str
    original_input: str
    video_path: Path
    display_name: str
    source_info: dict[str, Any]
    caption_path: Path | None = None
    caption_source: str = "gemini_transcribe"


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

    stem = Path(raw).stem if Path(raw).suffix else raw
    for suffix in VIDEO_SUFFIXES:
        maybe = cwd / f"{stem}{suffix}"
        if maybe.exists():
            return maybe.resolve()

    matches = list(cwd.glob(f"{stem}.*"))
    video_matches = [m for m in matches if m.suffix.lower() in VIDEO_SUFFIXES]
    if len(video_matches) == 1:
        return video_matches[0].resolve()
    if len(video_matches) > 1:
        names = ", ".join(m.name for m in video_matches)
        raise RuntimeError(f"Multiple videos matched '{raw}': {names}. Please specify exact file.")

    raise FileNotFoundError(f"Video not found: {raw}")


def exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_file_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    fingerprint: dict[str, Any] = {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    if stat.st_size <= _SHA256_SIZE_LIMIT:
        fingerprint["sha256"] = file_sha256(path)
    return fingerprint


def build_video_fingerprint(video: Path) -> dict[str, Any]:
    fingerprint = build_file_fingerprint(video)
    fingerprint["name"] = video.name
    return fingerprint


def build_glossary_fingerprint(glossary_path: Path | None) -> dict[str, Any] | None:
    if not glossary_path:
        return None
    return build_file_fingerprint(glossary_path)


def load_manifest(path: Path) -> dict[str, Any]:
    if not exists_nonempty(path):
        return {"version": MANIFEST_VERSION, "artifacts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"version": MANIFEST_VERSION, "artifacts": {}}
    if not isinstance(data, dict):
        return {"version": MANIFEST_VERSION, "artifacts": {}}
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    return {
        "version": data.get("version", MANIFEST_VERSION),
        "video": data.get("video"),
        "source": data.get("source"),
        "artifacts": artifacts,
    }


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def artifact_record(
    *,
    config: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "config": config,
        "inputs": inputs,
    }


def artifact_is_current(
    *,
    path: Path,
    manifest: dict[str, Any],
    artifact_name: str,
    config: dict[str, Any],
    inputs: dict[str, Any],
) -> bool:
    if not exists_nonempty(path):
        return False
    record = manifest.get("artifacts", {}).get(artifact_name)
    if not isinstance(record, dict):
        return False
    return record == artifact_record(config=config, inputs=inputs)


def check_artifact(
    manifest: dict[str, Any],
    name: str,
    path: Path,
    config: dict[str, Any],
    inputs: dict[str, Any],
    *,
    required_input_keys: Sequence[str] = (),
) -> bool:
    """Seed manifest for pre-existing artifacts and return whether the artifact is current."""
    can_seed = all(k in inputs for k in required_input_keys)
    if name not in manifest.get("artifacts", {}) and exists_nonempty(path) and can_seed:
        manifest.setdefault("artifacts", {})[name] = artifact_record(config=config, inputs=inputs)
    return artifact_is_current(
        path=path,
        manifest=manifest,
        artifact_name=name,
        config=config,
        inputs=inputs,
    )


def record_artifact(manifest: dict[str, Any], name: str, config: dict[str, Any], inputs: dict[str, Any]) -> None:
    manifest.setdefault("artifacts", {})[name] = artifact_record(config=config, inputs=inputs)


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


def build_download_meta_path(download_dir: Path, url: str) -> Path:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return download_dir / "_meta" / f"{url_hash}.source.json"


def load_source_meta(path: Path) -> dict[str, Any]:
    if not exists_nonempty(path):
        raise FileNotFoundError(f"YouTube download metadata not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid YouTube metadata payload: {path}")
    return data


def resolve_local_source(video_arg: str | None, video_option: str | None, cwd: Path) -> ResolvedSource:
    raw_input = video_arg or video_option or ""
    video = pick_video(video_arg, video_option, cwd)
    video_info = build_video_fingerprint(video)
    source_info = {
        "type": "local",
        "input": raw_input or str(video),
        "video": video_info,
        "caption_source": "gemini_transcribe",
    }
    return ResolvedSource(
        source_type="local",
        original_input=raw_input or str(video),
        video_path=video,
        display_name=video.name,
        source_info=source_info,
    )


def resolve_youtube_source(
    *,
    url: str,
    download_dir: Path,
    captions_mode: str,
    cookie_file: str | None,
    cookies_from_browser: str | None,
    resume: bool,
    root: Path,
) -> ResolvedSource:
    meta_path = build_download_meta_path(download_dir, url)
    cmd = [
        "python",
        str(SCRIPT_ROOT / "download_youtube.py"),
        "--url",
        url,
        "--download-dir",
        str(download_dir),
        "--out-meta",
        str(meta_path),
        "--captions-mode",
        captions_mode,
    ]
    if cookie_file:
        cmd.extend(["--cookies", cookie_file])
    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    if resume:
        cmd.append("--resume")
    else:
        cmd.append("--force")
    run(cmd, cwd=root)

    payload = load_source_meta(meta_path)
    video_path = Path(str(payload.get("downloaded_video_path", ""))).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Downloaded YouTube video not found: {video_path}")

    english_caption_path = payload.get("english_caption_path")
    caption_path = Path(str(english_caption_path)).resolve() if english_caption_path else None
    youtube_caption_source = str(payload.get("caption_source") or "none")
    actual_caption_source = youtube_caption_source if caption_path else "gemini_transcribe"
    video_info = build_video_fingerprint(video_path)
    source_info: dict[str, Any] = {
        "type": "youtube",
        "source_url": str(payload.get("source_url") or url),
        "video_id": str(payload.get("video_id") or ""),
        "title": str(payload.get("title") or video_path.stem),
        "video": video_info,
        "youtube_caption_source": youtube_caption_source,
        "caption_source": actual_caption_source,
    }
    if caption_path and exists_nonempty(caption_path):
        source_info["english_caption"] = build_file_fingerprint(caption_path)

    return ResolvedSource(
        source_type="youtube",
        original_input=url,
        video_path=video_path,
        display_name=source_info["title"],
        source_info=source_info,
        caption_path=caption_path if caption_path and exists_nonempty(caption_path) else None,
        caption_source=actual_caption_source,
    )


def build_preserved_args(args: argparse.Namespace) -> list[str]:
    preserved: list[str] = []
    if args.model != get_default_model():
        preserved.extend(["--model", args.model])
    if args.batch_size != 20:
        preserved.extend(["--batch-size", str(args.batch_size)])
    if args.zh_size != 48:
        preserved.extend(["--zh-size", str(args.zh_size)])
    if args.en_size != 34:
        preserved.extend(["--en-size", str(args.en_size)])
    if args.glossary:
        preserved.extend(["--glossary", str(Path(args.glossary).resolve())])
    if args.no_glossary:
        preserved.append("--no-glossary")
    if args.no_copy:
        preserved.append("--no-copy")
    elif args.copy:
        preserved.append("--copy")
    if args.review_lines != 12:
        preserved.extend(["--review-lines", str(args.review_lines)])
    if args.download_dir != DEFAULT_DOWNLOAD_DIR:
        preserved.extend(["--download-dir", str(Path(args.download_dir).resolve())])
    if args.no_youtube_captions:
        preserved.append("--no-youtube-captions")
    if args.cookies:
        preserved.extend(["--cookies", args.cookies])
    if args.cookies_from_browser:
        preserved.extend(["--cookies-from-browser", args.cookies_from_browser])
    return preserved


def build_next_command(source: ResolvedSource, args: argparse.Namespace) -> str:
    cmd = ["python", str(SCRIPT_ROOT / "run_pipeline.py")]
    if source.source_type == "youtube":
        cmd.extend(["--url", source.original_input])
    else:
        cmd.append(str(source.video_path))
    cmd.extend(build_preserved_args(args))
    cmd.extend(["--approve-burn", "--resume"])
    return subprocess.list2cmdline(cmd)


def ensure_english_srt(source: ResolvedSource, output_path: Path) -> None:
    if source.caption_path is None or not exists_nonempty(source.caption_path):
        raise RuntimeError("No reusable English caption file is available.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.caption_path, output_path)
    print(f"[info] copied YouTube English captions -> {output_path}")


def process_source(source: ResolvedSource, args: argparse.Namespace, root: Path) -> str:
    video = source.video_path
    stem = video.stem
    subs_dir = root / "subs"
    output_dir = root / "output"
    final_videos_dir = root / "final_videos"
    logs_dir = output_dir / "logs"
    subs_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_videos_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    en_srt = subs_dir / f"{stem}.en.raw.srt"
    bi_srt = subs_dir / f"{stem}.zh_en.srt"
    bi_ass = subs_dir / f"{stem}.zh_en.ass"
    out_mp4 = final_videos_dir / f"{stem}.zh-en-hard.mp4"
    out_log = logs_dir / f"{stem}.zh-en-hard.ffmpeg.log"
    out_copy = output_dir / f"{stem}.copy.json"
    review_txt = output_dir / f"{stem}.subtitle-review.txt"
    manifest_path = output_dir / f"{stem}.pipeline-manifest.json"
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

    video_info = build_video_fingerprint(video)
    source_info = dict(source.source_info)
    source_info["video"] = video_info
    if source.caption_path and exists_nonempty(source.caption_path):
        source_info["english_caption"] = build_file_fingerprint(source.caption_path)
    glossary_info = build_glossary_fingerprint(glossary_path)
    manifest = load_manifest(manifest_path)
    manifest = {
        "version": MANIFEST_VERSION,
        "video": video_info,
        "source": source_info,
        "artifacts": manifest.get("artifacts", {}),
    }

    en_config: dict[str, Any] = {"caption_source": source.caption_source}
    if source.caption_source == "gemini_transcribe":
        en_config["model"] = args.model
    en_inputs: dict[str, Any] = {
        "source": source_info,
        "video": video_info,
    }
    if source.caption_path and exists_nonempty(source.caption_path):
        en_inputs["external_caption"] = build_file_fingerprint(source.caption_path)
    en_current = check_artifact(manifest, "en_srt", en_srt, en_config, en_inputs)

    bi_config = {
        "model": args.model,
        "batch_size": args.batch_size,
        "glossary": glossary_info,
    }
    bi_inputs: dict[str, Any] = {
        "source": source_info,
        "video": video_info,
    }
    if exists_nonempty(en_srt):
        bi_inputs["en_srt"] = build_file_fingerprint(en_srt)
    bi_current = check_artifact(manifest, "bi_srt", bi_srt, bi_config, bi_inputs, required_input_keys=("en_srt",))

    ass_config = {
        "zh_size": args.zh_size,
        "en_size": args.en_size,
        "zh_font": "Microsoft YaHei",
        "en_font": "Arial",
    }
    ass_inputs: dict[str, Any] = {"source": source_info}
    if exists_nonempty(bi_srt):
        ass_inputs["bi_srt"] = build_file_fingerprint(bi_srt)
    ass_current = check_artifact(manifest, "bi_ass", bi_ass, ass_config, ass_inputs, required_input_keys=("bi_srt",))

    burn_config = {"approve_burn": True}
    burn_inputs: dict[str, Any] = {
        "source": source_info,
        "video": video_info,
    }
    if exists_nonempty(bi_ass):
        burn_inputs["bi_ass"] = build_file_fingerprint(bi_ass)
    burn_current = check_artifact(manifest, "out_mp4", out_mp4, burn_config, burn_inputs, required_input_keys=("bi_ass",))

    copy_config = {"model": args.model}
    copy_inputs: dict[str, Any] = {
        "source": source_info,
        "video": video_info,
    }
    if exists_nonempty(bi_srt):
        copy_inputs["bi_srt"] = build_file_fingerprint(bi_srt)
    copy_current = check_artifact(manifest, "out_copy", out_copy, copy_config, copy_inputs, required_input_keys=("bi_srt",))

    review_required = (not had_review_file) or review_is_stale

    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    needs_transcription = not (resume and en_current)
    needs_translation = not (resume and bi_current)
    needs_ass = not (resume and ass_current)
    needs_burn = args.approve_burn and not (resume and burn_current)
    needs_copy = do_copy and not (resume and copy_current)

    env_cmd = ["python", str(SCRIPT_ROOT / "check_env.py"), "--strict"]
    if not (needs_transcription or needs_translation or needs_copy):
        env_cmd.append("--skip-api-key")
    if not needs_burn:
        env_cmd.extend(["--skip-ffmpeg", "--skip-ass-filter"])
    run(env_cmd, cwd=root)

    if needs_transcription:
        if source.caption_path and exists_nonempty(source.caption_path):
            ensure_english_srt(source, en_srt)
        else:
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
        record_artifact(manifest, "en_srt", en_config, en_inputs)
        review_required = True
    else:
        print(f"[skip] transcription exists: {en_srt}")

    bi_inputs = {
        "source": source_info,
        "video": video_info,
        "en_srt": build_file_fingerprint(en_srt),
    }
    bi_current = check_artifact(manifest, "bi_srt", bi_srt, bi_config, bi_inputs, required_input_keys=("en_srt",))
    if not (resume and bi_current):
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
        record_artifact(manifest, "bi_srt", bi_config, bi_inputs)
        review_required = True
    else:
        print(f"[skip] bilingual srt exists: {bi_srt}")

    ass_inputs = {
        "source": source_info,
        "bi_srt": build_file_fingerprint(bi_srt),
    }
    ass_current = check_artifact(manifest, "bi_ass", bi_ass, ass_config, ass_inputs, required_input_keys=("bi_srt",))
    if not (resume and ass_current):
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
        record_artifact(manifest, "bi_ass", ass_config, ass_inputs)
        review_required = True
    else:
        print(f"[skip] ass exists: {bi_ass}")

    total_entries, first_zh = write_review_file(bi_srt, review_txt, args.review_lines)
    record_artifact(manifest, "review_txt", {"review_lines": args.review_lines}, {
        "source": source_info,
        "bi_srt": build_file_fingerprint(bi_srt),
        "bi_ass": build_file_fingerprint(bi_ass),
    })
    save_manifest(manifest_path, manifest)
    print(f"[review] subtitle file ready: {bi_srt}")
    print(f"[review] subtitle sample file: {review_txt}")
    print(f"[review] pipeline manifest: {manifest_path}")
    print(f"[review] total entries: {total_entries}")
    print(f"[review] first zh line: {first_zh}")

    next_cmd = build_next_command(source, args)

    if review_required:
        print("[hold] Review required because subtitle outputs were created or updated in this run.")
        print(f"[action] Open the review sample and check translations before burning: {review_txt}")
        print(f"[next] After review, rerun: {next_cmd}")
        return "review_pending"

    if not args.approve_burn:
        print("[hold] Burn step is blocked until you confirm subtitles.")
        print(f"[action] Open the review sample and check translations before burning: {review_txt}")
        print(f"[next] After confirmation, run: {next_cmd}")
        return "review_pending"

    burn_inputs = {
        "source": source_info,
        "video": video_info,
        "bi_ass": build_file_fingerprint(bi_ass),
    }
    burn_current = check_artifact(manifest, "out_mp4", out_mp4, burn_config, burn_inputs, required_input_keys=("bi_ass",))
    if not (resume and burn_current):
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
        record_artifact(manifest, "out_mp4", burn_config, burn_inputs)
    else:
        print(f"[skip] hard-sub video exists: {out_mp4}")

    if do_copy:
        copy_inputs = {
            "source": source_info,
            "video": video_info,
            "bi_srt": build_file_fingerprint(bi_srt),
        }
        copy_current = check_artifact(manifest, "out_copy", out_copy, copy_config, copy_inputs, required_input_keys=("bi_srt",))
        if not (resume and copy_current):
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
            record_artifact(manifest, "out_copy", copy_config, copy_inputs)
        else:
            print(f"[skip] copy exists: {out_copy}")

    save_manifest(manifest_path, manifest)
    print("[done] pipeline completed.")
    print(f"[done] hard subtitle video: {out_mp4}")
    if do_copy:
        print(f"[done] copy package: {out_copy}")
    return "completed"


def print_batch_summary(results: list[tuple[str, str]], failures: list[tuple[str, str]]) -> None:
    completed = sum(1 for _, status in results if status == "completed")
    review_pending = sum(1 for _, status in results if status == "review_pending")
    print(
        f"[summary] completed={completed} review_pending={review_pending} failed={len(failures)}"
    )
    for label, status in results:
        print(f"[summary] {status}: {label}")
    for label, error in failures:
        print(f"[summary] failed: {label}")
        print(f"[summary] error: {error}")


def main() -> int:
    configure_stdio_utf8()
    parser = argparse.ArgumentParser(
        description="One-command bilingual subtitle pipeline. Chinese is larger and appears above English."
    )
    parser.add_argument("video", nargs="?", help="Local video file path (recommended positional input)")
    parser.add_argument("--video", dest="video_option", help="Local video file path")
    parser.add_argument("--url", action="append", help="YouTube URL to download and process. Repeat for multiple videos.")
    parser.add_argument("--download-dir", default=DEFAULT_DOWNLOAD_DIR, help="Directory for downloaded YouTube source videos")
    parser.add_argument("--use-youtube-captions", action="store_true", help="Prefer YouTube English captions when available (default)")
    parser.add_argument("--no-youtube-captions", action="store_true", help="Disable YouTube caption download and always transcribe audio with Gemini")
    parser.add_argument("--cookies", help="Path to Netscape-format cookies.txt for YouTube authentication")
    parser.add_argument("--cookies-from-browser", help="Load YouTube cookies from a browser for downloads, e.g. chrome or chrome:Default")
    parser.add_argument("--model", default=get_default_model())
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
    if args.video and args.video_option:
        raise RuntimeError("Provide either <video> or --video, not both.")
    if args.no_youtube_captions and args.use_youtube_captions:
        raise RuntimeError("Use either --use-youtube-captions or --no-youtube-captions, not both.")
    if args.cookies and args.cookies_from_browser:
        raise RuntimeError("Use either --cookies or --cookies-from-browser, not both.")

    root = Path.cwd()
    local_input = args.video or args.video_option
    url_inputs = args.url or []
    if local_input and url_inputs:
        raise RuntimeError("Use either local video input or --url, not both in the same command.")
    if not local_input and not url_inputs:
        raise RuntimeError("Missing input. Provide a local video path or at least one --url.")

    resume = args.resume or (not args.force)
    captions_mode = "prefer"
    if args.no_youtube_captions:
        captions_mode = "off"

    if url_inputs:
        run(
            [
                "python",
                str(SCRIPT_ROOT / "check_env.py"),
                "--strict",
                "--need-youtube",
                "--skip-api-key",
                "--skip-ffmpeg",
                "--skip-ass-filter",
            ],
            cwd=root,
        )

    pending: list[tuple[str, str]] = []
    failures: list[tuple[str, str]] = []
    tasks: list[tuple[str, str]] = [("local", local_input)] if local_input else [("youtube", url) for url in url_inputs]
    download_dir = (root / args.download_dir).resolve() if not Path(args.download_dir).is_absolute() else Path(args.download_dir).resolve()

    for mode, raw_input in tasks:
        try:
            if mode == "local":
                source = resolve_local_source(args.video, args.video_option, root)
            else:
                print(f"[source] youtube: {raw_input}")
                source = resolve_youtube_source(
                    url=raw_input,
                    download_dir=download_dir,
                    captions_mode=captions_mode,
                    cookie_file=args.cookies,
                    cookies_from_browser=args.cookies_from_browser,
                    resume=resume,
                    root=root,
                )
            status = process_source(source, args, root)
            pending.append((source.display_name, status))
        except Exception as exc:
            if len(tasks) == 1:
                raise
            failures.append((raw_input, str(exc)))
            print(f"[error] failed for {raw_input}: {exc}")

    if len(tasks) > 1 or failures:
        print_batch_summary(pending, failures)

    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
