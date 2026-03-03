#!/usr/bin/env python3
"""Translate English SRT to Chinese and output bilingual SRT."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import (
    SrtEntry,
    extract_json_text,
    extract_text_from_response,
    generate_content,
    get_api_key,
    parse_srt,
    retry,
    split_batches,
    write_srt,
)

DEFAULT_MODEL = "gemini-3-pro-preview"

SYSTEM_PROMPT = (
    "You are a professional subtitle translator. Translate English subtitle lines into concise "
    "Simplified Chinese for short videos."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "zh_text": {"type": "string"},
                },
                "required": ["id", "zh_text"],
            },
        }
    },
    "required": ["items"],
}


def load_glossary(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Glossary must be a JSON object: {path}")
    return {str(k): str(v) for k, v in raw.items()}


def build_prompt(batch: list[SrtEntry], glossary: dict[str, str]) -> str:
    input_items = [
        {
            "id": entry.index,
            "en_text": " ".join(entry.text.split()),
        }
        for entry in batch
    ]
    constraints = [
        "Return strict JSON only.",
        "Keep translation natural and concise for on-screen subtitles.",
        "Do not add speaker labels or explanations.",
        "Preserve sentence meaning.",
    ]
    if glossary:
        constraints.append("Apply glossary replacements with high priority.")

    payload: dict[str, Any] = {
        "task": "Translate English subtitles into Simplified Chinese.",
        "constraints": constraints,
        "input_items": input_items,
    }
    if glossary:
        payload["glossary"] = glossary

    return json.dumps(payload, ensure_ascii=False)


def parse_batch_result(raw_text: str) -> dict[int, str]:
    payload = extract_json_text(raw_text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected translation payload type: {type(payload)}")
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise RuntimeError("Translation payload missing items list.")
    out: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item["id"])
            zh_text = " ".join(str(item["zh_text"]).split()).strip()
        except Exception:  # noqa: BLE001
            continue
        if zh_text:
            out[idx] = zh_text
    return out


def translate_batch(
    *,
    api_key: str,
    model: str,
    batch: list[SrtEntry],
    glossary: dict[str, str],
    label: str,
) -> dict[int, str]:
    prompt = build_prompt(batch, glossary)
    response = retry(
        lambda: generate_content(
            api_key=api_key,
            model=model,
            parts=[{"text": prompt}],
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
        attempts=3,
        label=label,
    )
    raw_text = extract_text_from_response(response)
    return parse_batch_result(raw_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="input_srt", required=True)
    parser.add_argument("--out", dest="output_srt", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--glossary", type=Path)
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be > 0")

    input_srt = Path(args.input_srt)
    output_srt = Path(args.output_srt)
    entries = parse_srt(input_srt)
    if not entries:
        raise RuntimeError(f"No subtitle entries found: {input_srt}")

    api_key = get_api_key(args.api_key)
    glossary = load_glossary(args.glossary)

    translated: dict[int, str] = {}

    for batch_index, batch in enumerate(split_batches(entries, args.batch_size), start=1):
        print(f"[info] translating batch {batch_index} ({len(batch)} entries) ...")
        mapped = translate_batch(
            api_key=api_key,
            model=args.model,
            batch=batch,
            glossary=glossary,
            label=f"translation batch {batch_index}",
        )
        translated.update(mapped)

    missing_entries = [entry for entry in entries if entry.index not in translated]
    if missing_entries:
        print(f"[warn] first pass missing {len(missing_entries)} entries; retrying one-by-one ...")
    for entry in missing_entries:
        try:
            mapped = translate_batch(
                api_key=api_key,
                model=args.model,
                batch=[entry],
                glossary=glossary,
                label=f"translation fallback id={entry.index}",
            )
            if entry.index in mapped and mapped[entry.index].strip():
                translated[entry.index] = mapped[entry.index].strip()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] fallback translation failed for id={entry.index}: {exc}")

    output_entries: list[SrtEntry] = []
    missing = 0
    for entry in entries:
        zh = translated.get(entry.index, "").strip()
        if not zh:
            missing += 1
            zh = entry.text
        bilingual_text = f"{zh}\n{entry.text}"
        output_entries.append(
            SrtEntry(index=entry.index, start_ms=entry.start_ms, end_ms=entry.end_ms, text=bilingual_text)
        )

    write_srt(output_srt, output_entries)
    print(f"[done] wrote bilingual subtitles -> {output_srt}")
    if missing:
        print(f"[warn] missing translations for {missing} entries; used English fallback.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
