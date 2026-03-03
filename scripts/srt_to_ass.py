#!/usr/bin/env python3
"""Convert bilingual SRT (Chinese first line, English second line) to styled ASS."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import parse_srt


def ms_to_ass_time(ms: int) -> str:
    ms = max(0, int(ms))
    hours = ms // 3_600_000
    ms -= hours * 3_600_000
    minutes = ms // 60_000
    ms -= minutes * 60_000
    seconds = ms // 1000
    ms -= seconds * 1000
    centiseconds = round(ms / 10)
    if centiseconds >= 100:
        seconds += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def escape_ass_text(text: str) -> str:
    text = text.replace("\\", r"\\")
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")
    text = text.replace("\n", r"\N")
    return text


def wrap_zh(text: str, max_chars: int = 16) -> str:
    compact = "".join(text.split())
    if len(compact) <= max_chars:
        return compact
    chunks = [compact[i : i + max_chars] for i in range(0, len(compact), max_chars)]
    return "\n".join(chunks[:2])


def wrap_en(text: str, max_chars: int = 42) -> str:
    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        next_len = len(word) if not current else current_len + 1 + len(word)
        if next_len <= max_chars:
            current.append(word)
            current_len = next_len
        else:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines[:2])


def build_header(zh_font: str, en_font: str, zh_size: int, en_size: int) -> str:
    return f"""[Script Info]
Title: Bilingual subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: ZhMain,{zh_font},{zh_size},&H00FFFFFF,&H000000FF,&H00141414,&H78000000,0,0,0,0,100,100,0,0,1,2.2,0.5,2,60,60,78,1
Style: EnSub,{en_font},{en_size},&H00E8E8E8,&H000000FF,&H00141414,&H78000000,0,0,0,0,100,100,0,0,1,1.8,0.3,2,60,60,34,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="input_srt", required=True)
    parser.add_argument("--out", dest="output_ass", required=True)
    parser.add_argument("--zh-size", type=int, default=48)
    parser.add_argument("--en-size", type=int, default=34)
    parser.add_argument("--zh-font", default="Microsoft YaHei")
    parser.add_argument("--en-font", default="Arial")
    args = parser.parse_args()

    input_srt = Path(args.input_srt)
    output_ass = Path(args.output_ass)
    entries = parse_srt(input_srt)
    if not entries:
        raise RuntimeError(f"No subtitle entries found: {input_srt}")

    lines = [build_header(args.zh_font, args.en_font, args.zh_size, args.en_size)]
    for entry in entries:
        text_lines = entry.text.splitlines()
        zh_raw = text_lines[0] if text_lines else ""
        en_raw = " ".join(text_lines[1:]).strip() if len(text_lines) > 1 else ""

        zh = escape_ass_text(wrap_zh(zh_raw))
        en = escape_ass_text(wrap_en(en_raw))

        start = ms_to_ass_time(entry.start_ms)
        end = ms_to_ass_time(entry.end_ms)

        if zh:
            lines.append(f"Dialogue: 0,{start},{end},ZhMain,,0,0,0,,{zh}")
        if en:
            lines.append(f"Dialogue: 0,{start},{end},EnSub,,0,0,0,,{en}")

    output_ass.parent.mkdir(parents=True, exist_ok=True)
    output_ass.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] wrote ASS subtitles -> {output_ass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
