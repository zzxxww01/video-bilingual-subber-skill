#!/usr/bin/env python3
"""Transcribe local media into English SRT using Gemini."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    SrtEntry,
    delete_file,
    extract_json_text,
    extract_text_from_response,
    generate_content,
    get_api_key,
    guess_mime,
    retry,
    upload_file,
    wait_for_file_active,
    write_srt,
)

DEFAULT_MODEL = "gemini-3-pro-preview"

DEFAULT_SYSTEM = (
    "You are an accurate subtitle transcriber for English video/audio. "
    "Return only structured output."
)

DEFAULT_PROMPT = """
Transcribe spoken English from this media file.
Return strict JSON object:
{
  "segments": [
    {"start_ms": <int>, "end_ms": <int>, "text": "<english sentence>"}
  ]
}

Rules:
- Keep timeline in chronological order.
- Do not skip spoken content.
- Do not include explanations or markdown.
- Use punctuation naturally.
- Keep each segment reasonably short for subtitle reading.
""".strip()

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_ms": {"type": "integer"},
                    "end_ms": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["start_ms", "end_ms", "text"],
            },
        }
    },
    "required": ["segments"],
}


def normalize_segments(raw_segments: list[dict[str, Any]]) -> list[SrtEntry]:
    normalized: list[SrtEntry] = []
    for item in raw_segments:
        try:
            start_ms = int(item["start_ms"])
            end_ms = int(item["end_ms"])
            text = " ".join(str(item["text"]).split()).strip()
        except Exception:  # noqa: BLE001
            continue
        if not text:
            continue
        if end_ms <= start_ms:
            end_ms = start_ms + 900
        normalized.append(SrtEntry(index=0, start_ms=start_ms, end_ms=end_ms, text=text))

    normalized.sort(key=lambda x: x.start_ms)
    if not normalized:
        return normalized

    for i in range(len(normalized)):
        current = normalized[i]
        if i > 0:
            prev = normalized[i - 1]
            if current.start_ms < prev.end_ms:
                current.start_ms = prev.end_ms
            if current.end_ms <= current.start_ms:
                current.end_ms = current.start_ms + 900
        current.index = i + 1
    return normalized


def load_prompt(prompt_file: Path | None) -> str:
    if prompt_file:
        return prompt_file.read_text(encoding="utf-8").strip()
    return DEFAULT_PROMPT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="input_path", required=True, help="Input media file")
    parser.add_argument("--out", dest="output_path", required=True, help="Output English SRT path")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", help="Gemini API key (or use GEMINI_API_KEY env var)")
    parser.add_argument("--prompt-file", type=Path, help="Optional prompt file")
    parser.add_argument("--keep-upload", action="store_true", help="Keep uploaded Gemini file for debugging")
    args = parser.parse_args()

    input_path = Path(args.input_path)
    output_path = Path(args.output_path)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    api_key = get_api_key(args.api_key)
    mime_type = guess_mime(input_path)
    prompt = load_prompt(args.prompt_file)

    print(f"[info] uploading media: {input_path} ({mime_type})")
    file_meta = retry(
        lambda: upload_file(api_key, input_path, mime_type=mime_type),
        attempts=3,
        label="file upload",
    )
    file_name = file_meta.get("name", "")
    file_uri = file_meta.get("uri", "")
    if not file_name or not file_uri:
        raise RuntimeError(f"Unexpected uploaded file metadata: {file_meta}")

    print(f"[info] uploaded file={file_name}, waiting until ACTIVE ...")
    active_meta = retry(
        lambda: wait_for_file_active(api_key, file_name),
        attempts=3,
        label="wait for uploaded file",
    )
    mime_type = active_meta.get("mimeType", mime_type)

    parts = [
        {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
        {"text": prompt},
    ]
    print(f"[info] requesting transcription from model={args.model} ...")
    response = retry(
        lambda: generate_content(
            api_key=api_key,
            model=args.model,
            parts=parts,
            system_instruction=DEFAULT_SYSTEM,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
        attempts=3,
        label="transcription request",
    )

    raw_text = extract_text_from_response(response)
    parsed = extract_json_text(raw_text)
    if isinstance(parsed, dict):
        raw_segments = parsed.get("segments", [])
    elif isinstance(parsed, list):
        raw_segments = parsed
    else:
        raise RuntimeError(f"Unexpected transcription payload type: {type(parsed)}")

    segments = normalize_segments(raw_segments)
    if not segments:
        raise RuntimeError("No valid segments returned by transcription model.")

    write_srt(output_path, segments)
    print(f"[done] wrote {len(segments)} subtitle entries -> {output_path}")

    if not args.keep_upload:
        try:
            delete_file(api_key, file_name)
            print(f"[info] deleted uploaded file {file_name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] failed to delete uploaded file {file_name}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
