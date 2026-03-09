#!/usr/bin/env python3
"""Generate simple short-video copy: title, description, hashtags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import (
    configure_stdio_utf8,
    extract_json_text,
    extract_text_from_response,
    generate_content,
    get_api_key,
    get_default_model,
    parse_srt,
    retry,
)

SYSTEM_PROMPT = (
    "You are a Chinese short-video copywriter. Produce practical publish-ready text."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "description", "hashtags"],
}


def collect_context(video: Path | None, srt: Path | None) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if video:
        context["video_filename"] = video.name
    if srt and srt.exists():
        entries = parse_srt(srt)
        zh_lines: list[str] = []
        en_lines: list[str] = []
        for entry in entries[:60]:
            lines = entry.text.splitlines()
            if lines:
                zh_lines.append(lines[0])
            if len(lines) > 1:
                en_lines.append(" ".join(lines[1:]))
        context["sample_zh_lines"] = zh_lines[:40]
        context["sample_en_lines"] = en_lines[:40]
        context["subtitle_count"] = len(entries)
    return context


def build_prompt(context: dict[str, Any]) -> str:
    payload = {
        "task": "Generate short-video publishing copy in Simplified Chinese.",
        "output_requirements": {
            "title": "One attractive but truthful title, <= 28 Chinese characters.",
            "description": "One concise description, 50-120 Chinese characters.",
            "hashtags": "8-15 hashtags, each starts with #, no duplicates.",
        },
        "constraints": [
            "No exaggerated claims.",
            "Keep tone natural.",
            "Avoid clickbait spam wording.",
            "Output strict JSON only.",
        ],
        "context": context,
    }
    return json.dumps(payload, ensure_ascii=False)


def normalize_output(payload: dict[str, Any]) -> dict[str, Any]:
    title = " ".join(str(payload.get("title", "")).split()).strip()
    description = " ".join(str(payload.get("description", "")).split()).strip()
    raw_hashtags = payload.get("hashtags", [])
    hashtags: list[str] = []
    if isinstance(raw_hashtags, list):
        for tag in raw_hashtags:
            if not isinstance(tag, str):
                continue
            t = tag.strip()
            if not t:
                continue
            if not t.startswith("#"):
                t = "#" + t
            hashtags.append(t)
    hashtags = list(dict.fromkeys(hashtags))[:15]

    if not title:
        title = "短视频精彩片段"
    if not description:
        description = "视频内容精炼剪辑，欢迎观看并交流感受。"
    if len(hashtags) < 8:
        fallback = ["#短视频", "#精彩片段", "#视频推荐", "#内容分享", "#热门", "#日常", "#Vlog", "#记录"]
        for tag in fallback:
            if tag not in hashtags:
                hashtags.append(tag)
            if len(hashtags) >= 8:
                break
    return {
        "title": title,
        "description": description,
        "hashtags": hashtags,
    }


def safe_console_text(text: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def main() -> int:
    configure_stdio_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--video")
    parser.add_argument("--srt")
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default=get_default_model())
    parser.add_argument("--api-key")
    args = parser.parse_args()

    video = Path(args.video).resolve() if args.video else None
    srt = Path(args.srt).resolve() if args.srt else None
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if video and not video.exists():
        raise FileNotFoundError(video)
    if srt and not srt.exists():
        raise FileNotFoundError(srt)

    api_key = get_api_key(args.api_key)
    context = collect_context(video, srt)
    prompt = build_prompt(context)

    response = retry(
        lambda: generate_content(
            api_key=api_key,
            model=args.model,
            parts=[{"text": prompt}],
            system_instruction=SYSTEM_PROMPT,
            temperature=0.4,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
        attempts=3,
        label="copy generation",
    )
    raw_text = extract_text_from_response(response)
    payload = extract_json_text(raw_text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected copy output type: {type(payload)}")
    normalized = normalize_output(payload)
    out.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    print(f"[done] wrote copy package -> {out}")
    print(f"[info] title: {safe_console_text(normalized['title'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
