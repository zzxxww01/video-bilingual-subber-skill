#!/usr/bin/env python3
"""Shared helpers for Gemini subtitle and copy workflow."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
UPLOAD_ROOT = "https://generativelanguage.googleapis.com/upload/v1beta"
_ENV_LOADED = False
SENSITIVE_QUERY_KEYS = {"key", "api_key", "apikey", "token", "access_token"}
SENSITIVE_CLI_FLAGS = {
    "--api-key",
    "--api_key",
    "--token",
    "--access-token",
    "--access_token",
    "--password",
    "--secret",
}


@dataclass
class SrtEntry:
    index: int
    start_ms: int
    end_ms: int
    text: str


def sanitize_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if not parsed.query:
            return url
        items = parse_qsl(parsed.query, keep_blank_values=True)
        safe_items: list[tuple[str, str]] = []
        for key, value in items:
            if key.lower() in SENSITIVE_QUERY_KEYS:
                safe_items.append((key, "<redacted>"))
            else:
                safe_items.append((key, value))
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(safe_items, doseq=True),
                parsed.fragment,
            )
        )
    except Exception:  # noqa: BLE001
        return re.sub(
            r"([?&](?:key|api[_-]?key|token|access[_-]?token)=)[^&\s]+",
            r"\1<redacted>",
            url,
            flags=re.IGNORECASE,
        )


def sanitize_text(value: str) -> str:
    if not value:
        return value
    text = value
    text = re.sub(
        r"([?&](?:key|api[_-]?key|token|access[_-]?token)=)[^&\s]+",
        r"\1<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(GEMINI_API_KEY\s*=\s*)([^\s\"']+)",
        r"\1<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bAIza[0-9A-Za-z_-]{20,}\b", "<redacted_google_key>", text)
    text = re.sub(r"\bsk-[A-Za-z0-9]{20,}\b", "<redacted_openai_key>", text)
    text = re.sub(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", "<redacted_github_token>", text)
    return text


def format_command(args: list[str]) -> str:
    masked: list[str] = []
    hide_next = False
    for arg in args:
        if hide_next:
            masked.append("<redacted>")
            hide_next = False
            continue
        lower = arg.lower()
        if lower in SENSITIVE_CLI_FLAGS:
            masked.append(arg)
            hide_next = True
            continue
        replaced = False
        for flag in SENSITIVE_CLI_FLAGS:
            if lower.startswith(flag + "="):
                prefix = arg.split("=", 1)[0]
                masked.append(f"{prefix}=<redacted>")
                replaced = True
                break
        if not replaced:
            masked.append(arg)
    return " ".join(masked)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_dotenv_if_present() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    candidates = [
        Path.cwd() / ".env",
        Path.cwd() / ".env.local",
    ]
    for path in candidates:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
    _ENV_LOADED = True


def get_api_key(explicit_key: str | None = None) -> str:
    load_dotenv_if_present()
    if explicit_key:
        print("[warn] --api-key may leak via shell history. Prefer GEMINI_API_KEY in env/.env.local.")
    key = explicit_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Provide --api-key, export GEMINI_API_KEY, or set it in .env."
        )
    return key.strip()


def retry(
    operation: Callable[[], Any],
    *,
    attempts: int = 3,
    base_sleep: float = 2.0,
    label: str = "operation",
) -> Any:
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if i == attempts - 1:
                break
            sleep_seconds = base_sleep * (2**i)
            print(f"[warn] {label} failed on attempt {i + 1}/{attempts}: {sanitize_text(str(exc))}")
            print(f"[info] retrying in {sleep_seconds:.1f}s ...")
            time.sleep(sleep_seconds)
    raise RuntimeError(f"{label} failed after {attempts} attempts: {sanitize_text(str(last_err))}") from last_err


def request_raw(
    *,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout_sec: int = 300,
) -> tuple[dict[str, str], bytes]:
    req = Request(url=url, method=method, headers=headers or {}, data=data)
    safe_url = sanitize_url(url)
    try:
        with urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            return dict(resp.headers.items()), resp.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {safe_url}: {sanitize_text(body)}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error for {safe_url}: {sanitize_text(str(exc))}") from exc


def request_json(
    *,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_sec: int = 300,
) -> dict[str, Any]:
    data = None
    merged_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/json")
    _, body = request_raw(
        url=url,
        method=method,
        headers=merged_headers,
        data=data,
        timeout_sec=timeout_sec,
    )
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def guess_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    return "application/octet-stream"


def upload_file(api_key: str, path: Path, *, mime_type: str | None = None) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    mime_type = mime_type or guess_mime(path)
    file_size = path.stat().st_size
    start_headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json",
    }
    start_payload = {"file": {"display_name": path.name}}
    start_url = f"{UPLOAD_ROOT}/files?key={quote(api_key)}"
    headers, _ = request_raw(
        url=start_url,
        method="POST",
        headers=start_headers,
        data=json.dumps(start_payload).encode("utf-8"),
        timeout_sec=120,
    )
    upload_url = headers.get("X-Goog-Upload-URL") or headers.get("x-goog-upload-url")
    if not upload_url:
        raise RuntimeError("Upload start succeeded but no upload URL was returned.")

    upload_headers = {
        "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize",
        "Content-Type": mime_type,
    }
    file_bytes = path.read_bytes()
    _, upload_body = request_raw(
        url=upload_url,
        method="POST",
        headers=upload_headers,
        data=file_bytes,
        timeout_sec=900,
    )
    upload_json = json.loads(upload_body.decode("utf-8"))
    if "file" not in upload_json:
        raise RuntimeError(f"Unexpected upload response: {upload_json}")
    return upload_json["file"]


def wait_for_file_active(api_key: str, file_name: str, *, timeout_sec: int = 600, poll_sec: int = 3) -> dict[str, Any]:
    end_time = time.time() + timeout_sec
    file_path = file_name if file_name.startswith("files/") else f"files/{file_name}"
    url = f"{API_ROOT}/{file_path}?key={quote(api_key)}"
    while time.time() < end_time:
        payload = request_json(url=url, method="GET", timeout_sec=60)
        state = payload.get("state", "")
        if state == "ACTIVE":
            return payload
        if state and state not in {"PROCESSING", "STATE_UNSPECIFIED"}:
            raise RuntimeError(f"File entered unexpected state: {state}")
        time.sleep(poll_sec)
    raise TimeoutError(f"Timed out waiting for file to become ACTIVE: {file_name}")


def delete_file(api_key: str, file_name: str) -> None:
    file_path = file_name if file_name.startswith("files/") else f"files/{file_name}"
    url = f"{API_ROOT}/{file_path}?key={quote(api_key)}"
    request_json(url=url, method="DELETE", timeout_sec=60)


def generate_content(
    *,
    api_key: str,
    model: str,
    parts: list[dict[str, Any]],
    system_instruction: str | None = None,
    temperature: float = 0.2,
    response_mime_type: str | None = None,
    response_schema: dict[str, Any] | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    url = f"{API_ROOT}/models/{quote(model)}:generateContent?key={quote(api_key)}"
    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ]
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    generation_config: dict[str, Any] = {"temperature": temperature}
    if response_mime_type:
        generation_config["responseMimeType"] = response_mime_type
    if response_schema:
        generation_config["responseSchema"] = response_schema
    if max_output_tokens is not None:
        generation_config["maxOutputTokens"] = max_output_tokens
    payload["generationConfig"] = generation_config
    return request_json(url=url, method="POST", payload=payload, timeout_sec=900)


def extract_text_from_response(response: dict[str, Any]) -> str:
    candidates = response.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"No candidates in model response: {response}")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text_parts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    text = "".join(text_parts).strip()
    if not text:
        raise RuntimeError(f"No text part in model response: {response}")
    return text


def extract_json_text(raw_text: str) -> Any:
    raw_text = raw_text.strip()
    if not raw_text:
        raise RuntimeError("Model output was empty.")

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", raw_text, flags=re.DOTALL)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    bracket_match = re.search(r"(\{.*\}|\[.*\])", raw_text, flags=re.DOTALL)
    if bracket_match:
        return json.loads(bracket_match.group(1))

    raise RuntimeError(f"Could not parse JSON from model output: {raw_text[:500]}")


def split_batches(items: list[Any], batch_size: int) -> Iterable[list[Any]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def parse_timestamp_to_ms(value: str) -> int:
    value = value.strip().replace(".", ",")
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2}),(\d{1,3})", value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, millis = [int(x) for x in match.groups()]
    if millis < 10:
        millis *= 100
    elif millis < 100:
        millis *= 10
    return ((hours * 3600 + minutes * 60 + seconds) * 1000) + millis


def ms_to_srt_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    hours = ms // 3_600_000
    ms -= hours * 3_600_000
    minutes = ms // 60_000
    ms -= minutes * 60_000
    seconds = ms // 1000
    millis = ms - seconds * 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_srt(path: Path) -> list[SrtEntry]:
    if not path.exists():
        raise FileNotFoundError(path)
    raw = path.read_text(encoding="utf-8-sig")
    raw = raw.replace("\r\n", "\n").strip()
    if not raw:
        return []
    blocks = re.split(r"\n{2,}", raw)
    result: list[SrtEntry] = []
    for block in blocks:
        lines = [line.rstrip("\n") for line in block.split("\n")]
        if len(lines) < 2:
            continue

        if re.fullmatch(r"\d+", lines[0].strip()):
            idx = int(lines[0].strip())
            timeline = lines[1]
            text_lines = lines[2:]
        else:
            idx = len(result) + 1
            timeline = lines[0]
            text_lines = lines[1:]

        timeline_match = re.match(r"(.+?)\s*-->\s*(.+?)(?:\s+.*)?$", timeline)
        if not timeline_match:
            continue

        start_ms = parse_timestamp_to_ms(timeline_match.group(1).strip())
        end_ms = parse_timestamp_to_ms(timeline_match.group(2).strip())
        text = "\n".join(text_lines).strip()
        if not text:
            continue
        if end_ms <= start_ms:
            end_ms = start_ms + 800
        result.append(SrtEntry(index=idx, start_ms=start_ms, end_ms=end_ms, text=text))

    # Normalize indices after parse.
    for i, entry in enumerate(result, start=1):
        entry.index = i
    return result


def write_srt(path: Path, entries: list[SrtEntry]) -> None:
    ensure_parent(path)
    lines: list[str] = []
    for i, entry in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{ms_to_srt_timestamp(entry.start_ms)} --> {ms_to_srt_timestamp(entry.end_ms)}")
        lines.append(entry.text.strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def resolve_ffmpeg(explicit_path: str | None = None) -> str:
    if explicit_path:
        if Path(explicit_path).exists():
            return explicit_path
        raise FileNotFoundError(f"ffmpeg not found at --ffmpeg path: {explicit_path}")

    env_ffmpeg = os.getenv("FFMPEG_BIN")
    if env_ffmpeg and Path(env_ffmpeg).exists():
        return env_ffmpeg

    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg

    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg or pip install imageio-ffmpeg."
        ) from exc


def resolve_ffprobe(ffmpeg_path: str) -> str | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe
    ffmpeg_candidate = Path(ffmpeg_path)
    sibling = ffmpeg_candidate.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if sibling.exists():
        return str(sibling)
    return None


def run_subprocess(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        safe_cmd = format_command(args)
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {safe_cmd}\n"
            f"stdout:\n{sanitize_text(proc.stdout or '')}\n"
            f"stderr:\n{sanitize_text(proc.stderr or '')}"
        )
    return proc
