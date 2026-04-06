#!/usr/bin/env python3
"""Regenerate Latvian A2 exam audio locally with Piper."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_DIR = ROOT / "codex"
MODEL_DIR = Path.home() / ".cache" / "lvcodex" / "piper"
DEFAULT_MODEL_NAME = "lv_LV-rudolfs-medium"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/RaivisDejus/Piper-lv_LV-Rudolfs-medium/resolve/main/"
)

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


def download_if_missing(target: Path, url: str) -> None:
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())


def ensure_model(model_dir: Path, model_name: str) -> tuple[Path, Path]:
    model_path = model_dir / f"{model_name}.onnx"
    config_path = model_dir / f"{model_name}.onnx.json"
    download_if_missing(model_path, f"{DEFAULT_MODEL_URL}{model_name}.onnx")
    download_if_missing(config_path, f"{DEFAULT_MODEL_URL}{model_name}.onnx.json")
    return model_path, config_path


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
    text = re.sub(
        r"(?m)^\s*(\d+)\.\s+",
        lambda m: f"Jautājums {m.group(1)}. ",
        text,
    )
    text = text.replace("`", "")
    text = re.sub(r"\.\s*\.\s*\.\s*\?\s*\.\s*\.\s*\.", "nav norādīts", text)
    text = re.sub(r"\.\s*\.\s*\.", "nav norādīts", text)
    text = re.sub(r"\?\s*", "? ", text)
    text = re.sub(r"!\s*", "! ", text)
    text = re.sub(r"\.\s*", ". ", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip() + "\n"


def collect_audio_jobs(md_path: Path) -> list[tuple[str, Path, str]]:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    attachments_dir = CODEX_DIR / "Attachments" / md_path.stem

    transcript_lines = section_between(lines, "## Listening Transcripts", ("## ",))
    speaking_lines = section_between(lines, "### Runātprasmes pārbaude", ("## ",))

    jobs = [
        (
            "klausisanas_1_uzdevums.mp3",
            attachments_dir / "klausisanas_1_uzdevums.mp3",
            normalize_for_speech(
                markdown_to_text(
                    section_between(transcript_lines, "### 1. uzdevums", ("### 2. uzdevums", "## "))
                )
            ),
        ),
        (
            "klausisanas_2_uzdevums.mp3",
            attachments_dir / "klausisanas_2_uzdevums.mp3",
            normalize_for_speech(
                markdown_to_text(
                    section_between(transcript_lines, "### 2. uzdevums", ("### 3. uzdevums", "## "))
                )
            ),
        ),
        (
            "klausisanas_3_uzdevums.mp3",
            attachments_dir / "klausisanas_3_uzdevums.mp3",
            normalize_for_speech(
                markdown_to_text(
                    section_between(transcript_lines, "### 3. uzdevums", ("## ",))
                )
            ),
        ),
        (
            "runasana_1_jautajumi.mp3",
            attachments_dir / "runasana_1_jautajumi.mp3",
            normalize_for_speech(
                markdown_to_text(
                    section_between(speaking_lines, "#### 1. uzdevums", ("#### 2. uzdevums", "## "))
                )
            ),
        ),
        (
            "runasana_2_jautajumi.mp3",
            attachments_dir / "runasana_2_jautajumi.mp3",
            normalize_for_speech(
                markdown_to_text(
                    section_between(speaking_lines, "#### 2. uzdevums", ("#### 3. uzdevums", "## "))
                )
            ),
        ),
        (
            "runasana_3_jautajumi.mp3",
            attachments_dir / "runasana_3_jautajumi.mp3",
            normalize_for_speech(
                markdown_to_text(
                    section_between(speaking_lines, "#### 3. uzdevums", ("## ",))
                )
            ),
        ),
    ]
    return jobs


def synthesize(text: str, model_path: Path, wav_path: Path, piper_bin: str) -> None:
    subprocess.run(
        [
            piper_bin,
            "--model",
            str(model_path),
            "--output_file",
            str(wav_path),
            "--sentence_silence",
            "0.45",
        ],
        input=text.encode("utf-8"),
        check=True,
    )


def wav_to_mp3(wav_path: Path, mp3_path: Path, ffmpeg_bin: str) -> None:
    tmp_path = mp3_path.with_suffix(".tmp.mp3")
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-i",
            str(wav_path),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11,acompressor=threshold=-18dB:ratio=2:attack=5:release=50",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    tmp_path.replace(mp3_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exam",
        action="append",
        help="Exam markdown filename to process, e.g. A2_Mock_Exam_01.md. Can be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print extracted text without generating audio.")
    parser.add_argument("--model-dir", default=str(MODEL_DIR), help="Directory for Piper model files.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME, help="Base Piper model name.")
    parser.add_argument("--piper-bin", default=shutil.which("piper") or "piper", help="Path to piper executable.")
    parser.add_argument("--ffmpeg-bin", default=shutil.which("ffmpeg") or "ffmpeg", help="Path to ffmpeg executable.")
    args = parser.parse_args()

    md_paths = [CODEX_DIR / exam for exam in args.exam] if args.exam else sorted(CODEX_DIR.glob("A2_Mock_Exam_*.md"))
    model_path = Path(args.model_dir) / f"{args.model_name}.onnx"
    if not args.dry_run:
        model_path, _ = ensure_model(Path(args.model_dir), args.model_name)

        for binary in (args.piper_bin, args.ffmpeg_bin):
            if shutil.which(binary) is None and not Path(binary).exists():
                raise SystemExit(f"Required binary not found: {binary}")

    for md_path in md_paths:
        jobs = collect_audio_jobs(md_path)
        print(f"{md_path.name}:")
        for name, target, text in jobs:
            preview = text.replace("\n", " ")[:140]
            print(f"  {name} <- {preview}...")
            if args.dry_run:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                wav_path = Path(tmpdir) / f"{target.stem}.wav"
                synthesize(text, model_path, wav_path, args.piper_bin)
                wav_to_mp3(wav_path, target, args.ffmpeg_bin)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
