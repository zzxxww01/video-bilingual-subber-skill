#!/usr/bin/env python3
"""Scan repository for secrets before publishing to GitHub."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_SCAN_BYTES = 1_500_000
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "subs",
    "output",
    "final_videos",
}
PLACEHOLDER_HINTS = {
    "your_",
    "example",
    "sample",
    "changeme",
    "placeholder",
    "<redacted>",
    "dummy",
}
RISKY_FILE_NAMES = {".env", ".env.local", ".env.production", ".env.prod", "id_rsa", "id_ed25519"}
RISKY_FILE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".der", ".jks", ".keystore"}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key_header", re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PGP )?PRIVATE KEY-----")),
    ("gemini_api_key_assignment", re.compile(r"GEMINI_API_KEY\s*=\s*([^\s\"']+)")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("query_secret", re.compile(r"[?&](?:key|api[_-]?key|token|access[_-]?token)=([^&\s]{16,})", flags=re.IGNORECASE)),
]


@dataclass
class Finding:
    path: Path
    line_no: int
    rule: str
    snippet: str


def is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in PLACEHOLDER_HINTS)


def is_dynamic_reference(value: str) -> bool:
    return any(ch in value for ch in "{}()$[]")


def is_ignored_path(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return any(part in SKIP_DIRS for part in rel.parts)


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if is_ignored_path(path):
            continue
        if path.stat().st_size > MAX_SCAN_BYTES:
            continue
        files.append(path)
    return files


def read_text(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    return data.decode("utf-8", errors="replace")


def scan_file(path: Path) -> list[Finding]:
    text = read_text(path)
    if text is None:
        return []

    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                matched = match.group(1) if match.lastindex else match.group(0)
                if is_placeholder(matched):
                    continue
                if is_dynamic_reference(matched):
                    continue
                snippet = line.strip()
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                findings.append(Finding(path=path, line_no=line_no, rule=rule, snippet=snippet))
    return findings


def collect_risky_local_files(root: Path) -> list[Path]:
    risky: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if is_ignored_path(path):
            continue
        name = path.name.lower()
        if name == ".env.example":
            continue
        if name in RISKY_FILE_NAMES or path.suffix.lower() in RISKY_FILE_SUFFIXES:
            risky.append(path)
    return risky


def main() -> int:
    parser = argparse.ArgumentParser(description="Check repository safety before uploading to GitHub.")
    parser.add_argument("--strict", action="store_true", help="Treat risky local files as failure.")
    args = parser.parse_args()

    findings: list[Finding] = []
    for file_path in iter_files(ROOT):
        findings.extend(scan_file(file_path))

    risky_files = collect_risky_local_files(ROOT)

    if findings:
        print("[fail] Potential secrets found:")
        for f in findings:
            rel = f.path.relative_to(ROOT)
            print(f"- {rel}:{f.line_no} [{f.rule}] {f.snippet}")
    else:
        print("[ok] No obvious secret patterns were found in scanned text files.")

    if risky_files:
        print("[warn] Risky local files detected (make sure they are not committed):")
        for path in risky_files:
            rel = path.relative_to(ROOT)
            print(f"- {rel}")
        if args.strict:
            print("[fail] --strict is enabled; risky local files are treated as failure.")

    if findings or (args.strict and risky_files):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
