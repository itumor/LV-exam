#!/usr/bin/env python3
"""Regenerate Latvian A2 exam audio with ElevenLabs."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_DIR = ROOT / "codex"
DEFAULT_MODEL_ID = "eleven_v3"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_SUFFIX = "_elevenlabs.mp3"
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"

ORDINALS_MASC = {
    1: "Pirmais",
    2: "Otrais",
    3: "Trešais",
    4: "Ceturtais",
    5: "Piektais",
    6: "Sestais",
    7: "Septītais",
    8: "Astotais",
    9: "Devītais",
    10: "Desmitais",
}

ORDINALS_FEM = {
    1: "Pirmā",
    2: "Otrā",
    3: "Trešā",
    4: "Ceturtā",
    5: "Piektā",
    6: "Sestā",
    7: "Septītā",
    8: "Astotā",
    9: "Devītā",
    10: "Desmitā",
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def section_between(lines: list[str], start_heading: str, end_heading_prefixes: tuple[str, ...]) -> list[str]:
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == start_heading:
            start = idx + 1
            break
    if start is None:
        raise ValueError(f"Could not find heading: {start_heading}")

    end = len(lines)
    for idx in range(start, len(lines)):
        stripped = lines[idx].strip()
        if any(stripped.startswith(prefix) for prefix in end_heading_prefixes):
            end = idx
            break
    return lines[start:end]


def strip_audio_markup(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    in_audio = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<audio"):
            in_audio = True
            continue
        if in_audio:
            if stripped == "</audio>":
                in_audio = False
            continue
        if stripped.startswith("[Audio failsafe link]"):
            continue
        if stripped.startswith("!["):
            continue
        cleaned.append(line)
    return cleaned


def markdown_to_text(lines: list[str]) -> str:
    text = "\n".join(strip_audio_markup(lines))
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = html.unescape(text)
    text = text.replace("–", ". ")
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_speech(text: str) -> str:
    def repl_label(match: re.Match[str]) -> str:
        num = int(match.group(1))
        label = match.group(2)
        ordinal_map = ORDINALS_MASC if label == "paziņojums" else ORDINALS_FEM
        ordinal = ordinal_map.get(num, str(num))
        return f"{ordinal} {label}."

    text = re.sub(r"(?m)^\s*(\d+)\.\s+(paziņojums|saruna)\s*$", repl_label, text)
    text = re.sub(r"(?m)^\s*(\d+)\.\s+", lambda m: f"Jautājums {m.group(1)}. ", text)
    text = text.replace("`", "")
    text = re.sub(r"\.\s*\.\s*\.\s*\?\s*\.\s*\.\s*\.", "nav norādīts", text)
    text = re.sub(r"\.\s*\.\s*\.", "nav norādīts", text)
    text = re.sub(r"\?\s*", "? ", text)
    text = re.sub(r"!\s*", "! ", text)
    text = re.sub(r"\.\s*", ". ", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip() + "\n"


def collect_audio_jobs(md_path: Path, suffix: str) -> list[tuple[str, Path, str]]:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    attachments_dir = CODEX_DIR / "Attachments" / md_path.stem

    transcript_lines = section_between(lines, "## Listening Transcripts", ("## ",))
    speaking_lines = section_between(lines, "### Runātprasmes pārbaude", ("## ",))

    def target(name: str) -> Path:
        stem = Path(name).stem
        return attachments_dir / f"{stem}{suffix}"

    return [
        (
            "klausisanas_1_uzdevums",
            target("klausisanas_1_uzdevums.mp3"),
            normalize_for_speech(
                markdown_to_text(
                    section_between(transcript_lines, "### 1. uzdevums", ("### 2. uzdevums", "## "))
                )
            ),
        ),
        (
            "klausisanas_2_uzdevums",
            target("klausisanas_2_uzdevums.mp3"),
            normalize_for_speech(
                markdown_to_text(
                    section_between(transcript_lines, "### 2. uzdevums", ("### 3. uzdevums", "## "))
                )
            ),
        ),
        (
            "klausisanas_3_uzdevums",
            target("klausisanas_3_uzdevums.mp3"),
            normalize_for_speech(
                markdown_to_text(section_between(transcript_lines, "### 3. uzdevums", ("## ",)))
            ),
        ),
        (
            "runasana_1_jautajumi",
            target("runasana_1_jautajumi.mp3"),
            normalize_for_speech(
                markdown_to_text(
                    section_between(speaking_lines, "#### 1. uzdevums", ("#### 2. uzdevums", "## "))
                )
            ),
        ),
        (
            "runasana_2_jautajumi",
            target("runasana_2_jautajumi.mp3"),
            normalize_for_speech(
                markdown_to_text(
                    section_between(speaking_lines, "#### 2. uzdevums", ("#### 3. uzdevums", "## "))
                )
            ),
        ),
        (
            "runasana_3_jautajumi",
            target("runasana_3_jautajumi.mp3"),
            normalize_for_speech(
                markdown_to_text(section_between(speaking_lines, "#### 3. uzdevums", ("## ",)))
            ),
        ),
    ]


def generate_audio(
    *,
    api_key: str,
    voice_id: str,
    text: str,
    model_id: str,
    output_format: str,
) -> bytes:
    query = urllib.parse.urlencode({"output_format": output_format})
    url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}?{query}"
    payload = json.dumps(
        {
            "text": text,
            "model_id": model_id,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
            "xi-api-key": api_key,
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def write_mp3(target: Path, audio_bytes: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp.mp3")
    tmp.write_bytes(audio_bytes)
    tmp.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exam",
        action="append",
        help="Exam markdown filename to process, e.g. A2_Mock_Exam_01.md. Can be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print extracted text without generating audio.")
    parser.add_argument(
        "--suffix",
        default=DEFAULT_SUFFIX,
        help="Suffix for generated MP3 files. Default: _elevenlabs.mp3",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    md_paths = [CODEX_DIR / exam for exam in args.exam] if args.exam else sorted(CODEX_DIR.glob("A2_Mock_Exam_*.md"))

    api_key = None if args.dry_run else require_env("ELEVENLABS_API_KEY")
    voice_id = None if args.dry_run else require_env("ELEVENLABS_VOICE_ID")
    model_id = os.environ.get("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID
    output_format = os.environ.get("ELEVENLABS_OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT).strip() or DEFAULT_OUTPUT_FORMAT

    for md_path in md_paths:
        jobs = collect_audio_jobs(md_path, args.suffix)
        print(f"{md_path.name}:")
        for name, target, text in jobs:
            preview = text.replace("\n", " ")[:140]
            print(f"  {name} -> {target.relative_to(ROOT)} <- {preview}...")
            if args.dry_run:
                continue
            try:
                audio_bytes = generate_audio(
                    api_key=api_key,
                    voice_id=voice_id,
                    text=text,
                    model_id=model_id,
                    output_format=output_format,
                )
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise SystemExit(f"ElevenLabs API request failed for {target.name}: HTTP {exc.code} {body}") from exc
            except urllib.error.URLError as exc:
                raise SystemExit(f"ElevenLabs API request failed for {target.name}: {exc}") from exc
            write_mp3(target, audio_bytes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
