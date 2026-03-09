#!/usr/bin/env python3
"""Download a YouTube video and optional English captions for the subtitle pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from common import (
    SrtEntry,
    configure_stdio_utf8,
    ensure_parent,
    get_optional_path_env,
    get_optional_text_env,
    write_srt,
)

try:
    import yt_dlp  # type: ignore
    from yt_dlp.cookies import SUPPORTED_BROWSERS, SUPPORTED_KEYRINGS  # type: ignore
except ImportError:  # pragma: no cover - exercised via runtime checks
    yt_dlp = None
    SUPPORTED_BROWSERS = set()
    SUPPORTED_KEYRINGS = set()


CAPTION_MODE_PREFER = "prefer"
CAPTION_MODE_REQUIRED = "required"
CAPTION_MODE_OFF = "off"
CAPTION_MODES = {CAPTION_MODE_PREFER, CAPTION_MODE_REQUIRED, CAPTION_MODE_OFF}
CAPTION_SUFFIXES = {".srt", ".vtt"}
VIDEO_SUFFIXES = {".mp4", ".m4v", ".mkv", ".webm", ".mov"}
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def require_yt_dlp() -> Any:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed. Run `pip install -r requirements.txt`.")
    return yt_dlp


def is_youtube_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]
    return host in YOUTUBE_HOSTS or host.endswith(".youtube.com")


def sanitize_title(value: str, *, max_length: int = 80) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r'[<>:"/\\|?*]', "_", text)
    text = text.replace("\0", "_")
    text = re.sub(r"_+", "_", text)
    text = text.strip(" ._")
    if not text:
        text = "youtube-video"
    return text[:max_length].rstrip(" ._") or "youtube-video"


def cache_key_for_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def pick_best_english_lang(tracks: dict[str, Any]) -> str | None:
    if not isinstance(tracks, dict):
        return None
    keys = [key for key in tracks if isinstance(key, str)]
    if not keys:
        return None
    preferred = ["en", "en-US", "en-GB", "en-CA", "en-AU", "en-orig"]
    lowered = {key.lower(): key for key in keys}
    for candidate in preferred:
        exact = lowered.get(candidate.lower())
        if exact:
            return exact
    english_keys = sorted(key for key in keys if key.lower().startswith("en"))
    return english_keys[0] if english_keys else None


def parse_cookies_from_browser(value: str | None) -> tuple[str, str | None, str | None, str | None] | None:
    if not value:
        return None
    match = re.fullmatch(
        r"""(?x)
        (?P<name>[^+:]+)
        (?:\s*\+\s*(?P<keyring>[^:]+))?
        (?:\s*:\s*(?!:)(?P<profile>.+?))?
        (?:\s*::\s*(?P<container>.+))?
        """,
        value,
    )
    if match is None:
        raise RuntimeError(f"Invalid --cookies-from-browser value: {value}")

    browser_name, keyring, profile, container = match.group("name", "keyring", "profile", "container")
    browser_name = browser_name.lower()
    if browser_name not in SUPPORTED_BROWSERS:
        supported = ", ".join(sorted(SUPPORTED_BROWSERS))
        raise RuntimeError(f"Unsupported browser for cookies: {browser_name}. Supported: {supported}")
    if keyring is not None:
        keyring = keyring.upper()
        if keyring not in SUPPORTED_KEYRINGS:
            supported = ", ".join(sorted(SUPPORTED_KEYRINGS))
            raise RuntimeError(f"Unsupported keyring for cookies: {keyring}. Supported: {supported}")
    return (browser_name, profile, keyring, container)


def resolve_cookie_file(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"Cookie file not found: {path}")
    return path


def detect_js_runtimes() -> dict[str, dict[str, str]]:
    runtimes: dict[str, dict[str, str]] = {}
    if shutil.which("deno"):
        runtimes["deno"] = {}
    if shutil.which("node"):
        runtimes["node"] = {}
    if shutil.which("bun"):
        runtimes["bun"] = {}
    return runtimes


def valid_cached_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None

    video_path = Path(str(data.get("downloaded_video_path", "")))
    if not video_path.exists():
        return None

    english_caption = data.get("english_caption_path")
    if english_caption:
        caption_path = Path(str(english_caption))
        if not caption_path.exists():
            return None
    return data


def parse_vtt_timestamp(value: str) -> int:
    value = value.strip()
    match = re.fullmatch(r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})", value)
    if not match:
        raise ValueError(f"Invalid WebVTT timestamp: {value}")
    hours_text, minutes_text, seconds_text, millis_text = match.groups()
    hours = int(hours_text or "0")
    minutes = int(minutes_text)
    seconds = int(seconds_text)
    millis = int(millis_text)
    return ((hours * 3600 + minutes * 60 + seconds) * 1000) + millis


def clean_vtt_text(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = cleaned.replace("&nbsp;", " ")
    return unescape(cleaned).strip()


def parse_webvtt(path: Path) -> list[SrtEntry]:
    raw = path.read_text(encoding="utf-8-sig")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n{2,}", normalized.strip())
    entries: list[SrtEntry] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        first = lines[0].strip()
        if first == "WEBVTT" or first.startswith("NOTE") or first.startswith("STYLE") or first.startswith("REGION"):
            continue

        if "-->" in lines[0]:
            timeline = lines[0]
            text_lines = lines[1:]
        elif len(lines) >= 2 and "-->" in lines[1]:
            timeline = lines[1]
            text_lines = lines[2:]
        else:
            continue

        start_text, end_text = [part.strip() for part in timeline.split("-->", 1)]
        end_text = end_text.split()[0]
        try:
            start_ms = parse_vtt_timestamp(start_text)
            end_ms = parse_vtt_timestamp(end_text)
        except ValueError:
            continue
        if end_ms <= start_ms:
            end_ms = start_ms + 800

        cleaned_lines = [clean_vtt_text(line) for line in text_lines]
        cleaned_lines = [line for line in cleaned_lines if line]
        if not cleaned_lines:
            continue
        entries.append(
            SrtEntry(
                index=len(entries) + 1,
                start_ms=start_ms,
                end_ms=end_ms,
                text="\n".join(cleaned_lines),
            )
        )
    return entries


def normalize_caption_to_srt(source_path: Path, output_path: Path) -> None:
    suffix = source_path.suffix.lower()
    ensure_parent(output_path)
    if suffix == ".srt":
        output_path.write_text(source_path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
        return
    if suffix == ".vtt":
        entries = parse_webvtt(source_path)
        if not entries:
            raise RuntimeError(f"No subtitle cues found in {source_path}")
        write_srt(output_path, entries)
        return
    raise RuntimeError(f"Unsupported YouTube subtitle format: {source_path.suffix}")


def find_downloaded_video(
    download_dir: Path,
    base_name: str,
    *,
    video_id: str,
    hinted_path: str | None = None,
) -> Path:
    if hinted_path:
        candidate = Path(hinted_path)
        if candidate.exists() and candidate.suffix.lower() in VIDEO_SUFFIXES:
            return candidate.resolve()

    prefix = f"{base_name}."
    candidates = [
        path
        for path in download_dir.glob(f"{base_name}.*")
        if path.is_file() and path.name.startswith(prefix) and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    if not candidates:
        candidates = [
            path
            for path in download_dir.iterdir()
            if path.is_file() and video_id in path.name and path.suffix.lower() in VIDEO_SUFFIXES
        ]
    if not candidates:
        raise FileNotFoundError(f"Downloaded video not found for {base_name}")
    candidates.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
    return candidates[0].resolve()


def find_caption_file(download_dir: Path, base_name: str, lang: str, *, video_id: str) -> Path | None:
    prefix = f"{base_name}."
    candidates: list[Path] = []
    for path in download_dir.glob(f"{base_name}.*"):
        if not path.is_file() or not path.name.startswith(prefix):
            continue
        if path.suffix.lower() not in CAPTION_SUFFIXES:
            continue
        remainder = path.stem[len(base_name) + 1 :]
        if not remainder.lower().startswith("en"):
            continue
        candidates.append(path)

    if not candidates:
        for path in download_dir.iterdir():
            if not path.is_file() or video_id not in path.name:
                continue
            if path.suffix.lower() not in CAPTION_SUFFIXES:
                continue
            stem_lower = path.stem.lower()
            if ".en" not in stem_lower and not stem_lower.endswith("en"):
                continue
            candidates.append(path)

    if not candidates:
        return None

    def sort_key(path: Path) -> tuple[int, int, str]:
        remainder = path.stem[len(base_name) + 1 :]
        exact = 0 if remainder == lang else 1
        extension_rank = 0 if path.suffix.lower() == ".srt" else 1
        return (exact, extension_rank, path.name.lower())

    candidates.sort(key=sort_key)
    return candidates[0].resolve()


def extract_video_metadata(
    url: str,
    cookie_file: Path | None = None,
    cookies_from_browser: tuple[str, str | None, str | None, str | None] | None = None,
) -> dict[str, Any]:
    yt_dlp_mod = require_yt_dlp()
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "ignoreconfig": True,
    }
    if cookie_file:
        options["cookiefile"] = str(cookie_file)
    if cookies_from_browser:
        options["cookiesfrombrowser"] = cookies_from_browser
    js_runtimes = detect_js_runtimes()
    if js_runtimes:
        options["js_runtimes"] = js_runtimes
    with yt_dlp_mod.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def download_video(
    *,
    url: str,
    download_dir: Path,
    base_name: str,
    video_id: str,
    subtitle_lang: str | None,
    subtitle_source: str,
    cookie_file: Path | None,
    cookies_from_browser: tuple[str, str | None, str | None, str | None] | None,
) -> tuple[dict[str, Any], Path, Path | None]:
    yt_dlp_mod = require_yt_dlp()
    outtmpl = str(download_dir / f"{base_name}.%(ext)s")
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": outtmpl,
        "windowsfilenames": True,
        "ignoreconfig": True,
        # Prefer a broadly compatible mp4 path first, then fall back to any best single file.
        "format": "best[ext=mp4][height<=1080]/best[height<=1080]/best",
    }
    if cookie_file:
        options["cookiefile"] = str(cookie_file)
    if cookies_from_browser:
        options["cookiesfrombrowser"] = cookies_from_browser
    js_runtimes = detect_js_runtimes()
    if js_runtimes:
        options["js_runtimes"] = js_runtimes
    if subtitle_lang:
        options["subtitleslangs"] = [subtitle_lang]
        options["subtitlesformat"] = "vtt/srt/best"
        options["writesubtitles"] = subtitle_source == "youtube_caption"
        options["writeautomaticsub"] = subtitle_source == "youtube_auto_caption"

    with yt_dlp_mod.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    hinted_video = None
    if isinstance(info, dict):
        hinted_video = info.get("filepath") or info.get("_filename")
    video_path = find_downloaded_video(download_dir, base_name, video_id=video_id, hinted_path=hinted_video)
    caption_path = None
    if subtitle_lang:
        caption_path = find_caption_file(download_dir, base_name, subtitle_lang, video_id=video_id)
    return info, video_path, caption_path


def main() -> int:
    configure_stdio_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="YouTube video URL")
    parser.add_argument("--download-dir", default="downloads", help="Directory for downloaded source videos")
    parser.add_argument("--out-meta", required=True, help="Output JSON metadata path")
    parser.add_argument("--captions-mode", default=CAPTION_MODE_PREFER, choices=sorted(CAPTION_MODES))
    parser.add_argument("--cookies", help="Path to Netscape-format cookies.txt for YouTube authentication")
    parser.add_argument("--cookies-from-browser", help="Load YouTube cookies from a browser, e.g. chrome or chrome:Default")
    parser.add_argument("--resume", action="store_true", help="Reuse cached download metadata when possible")
    parser.add_argument("--force", action="store_true", help="Force a fresh YouTube download")
    args = parser.parse_args()

    if args.resume and args.force:
        raise RuntimeError("Use either --resume or --force, not both.")
    if not is_youtube_url(args.url):
        raise RuntimeError("Only YouTube URLs are supported.")

    download_dir = Path(args.download_dir).resolve()
    meta_path = Path(args.out_meta).resolve()
    cookie_file = resolve_cookie_file(args.cookies) or get_optional_path_env(
        "YTDLP_COOKIE_FILE",
        "YOUTUBE_COOKIE_FILE",
    )
    cookies_from_browser_value = args.cookies_from_browser or get_optional_text_env(
        "YTDLP_COOKIES_FROM_BROWSER",
        "YOUTUBE_COOKIES_FROM_BROWSER",
    )
    if cookie_file and cookies_from_browser_value:
        raise RuntimeError("Use either --cookies / YTDLP_COOKIE_FILE or --cookies-from-browser, not both.")
    cookies_from_browser = parse_cookies_from_browser(cookies_from_browser_value)
    download_dir.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    if args.resume and not args.force:
        cached = valid_cached_meta(meta_path)
        if cached is not None:
            print(f"[skip] reuse cached YouTube download: {meta_path}")
            return 0

    info = extract_video_metadata(args.url, cookie_file=cookie_file, cookies_from_browser=cookies_from_browser)
    video_id = str(info.get("id") or "").strip()
    if not video_id:
        raise RuntimeError("Could not determine YouTube video id.")
    title = str(info.get("title") or f"youtube-{video_id}").strip()
    safe_title = sanitize_title(title)
    base_name = f"{safe_title} [{video_id}]"

    subtitle_lang = None
    subtitle_source = "none"
    if args.captions_mode != CAPTION_MODE_OFF:
        manual_lang = pick_best_english_lang(info.get("subtitles") or {})
        auto_lang = pick_best_english_lang(info.get("automatic_captions") or {})
        if manual_lang:
            subtitle_lang = manual_lang
            subtitle_source = "youtube_caption"
        elif auto_lang:
            subtitle_lang = auto_lang
            subtitle_source = "youtube_auto_caption"
        elif args.captions_mode == CAPTION_MODE_REQUIRED:
            raise RuntimeError("No English YouTube subtitles were available for this video.")

    _, video_path, raw_caption_path = download_video(
        url=args.url,
        download_dir=download_dir,
        base_name=base_name,
        video_id=video_id,
        subtitle_lang=subtitle_lang,
        subtitle_source=subtitle_source,
        cookie_file=cookie_file,
        cookies_from_browser=cookies_from_browser,
    )

    normalized_caption_path: Path | None = None
    if subtitle_lang and raw_caption_path is not None:
        normalized_caption_path = download_dir / f"{base_name}.en.raw.srt"
        normalize_caption_to_srt(raw_caption_path, normalized_caption_path)
    elif subtitle_source != "none" and args.captions_mode == CAPTION_MODE_REQUIRED:
        raise RuntimeError("YouTube subtitles were requested but could not be downloaded.")
    else:
        subtitle_source = "none"

    meta = {
        "source_type": "youtube",
        "source_url": args.url,
        "cache_key": cache_key_for_url(args.url),
        "video_id": video_id,
        "title": title,
        "downloaded_video_path": str(video_path),
        "english_caption_path": str(normalized_caption_path) if normalized_caption_path else None,
        "caption_source": subtitle_source,
        "download_dir": str(download_dir),
        "cookie_file": str(cookie_file) if cookie_file else None,
        "cookies_from_browser": cookies_from_browser_value,
    }
    ensure_parent(meta_path)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] downloaded YouTube video: {video_path}")
    if normalized_caption_path:
        print(f"[done] downloaded English captions: {normalized_caption_path}")
    else:
        print("[info] no English YouTube captions available; downstream should fall back to Gemini transcription.")
    print(f"[done] metadata: {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
