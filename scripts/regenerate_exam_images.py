#!/usr/bin/env python3
"""Regenerate exam attachment PNGs from Markdown descriptions using Ollama."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_DIR = ROOT / "codex"
OLLAMA_URL = "http://localhost:11434/v1/images/generations"
MODEL = "x/z-image-turbo:bf16"
#MODEL = "x/z-image-turbo:latest"
GENERATE_SIZE = "512x512"
UPSCALE_SIZE = 1024

WRITING_IMAGE_RE = re.compile(r"!\[[^\]]+\]\((Attachments/[^)]+/rakstisana_1_attels_\d+\.png)\)")
SPEAKING_IMAGE_RE = re.compile(r"!\[[^\]]+\]\((Attachments/[^)]+/runasana_2_attels_[12]\.png)\)")
NUMBERED_DESC_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
SPEAKING_DESC_RE = re.compile(r"^\*\*Attēls ([AB])\.\*\*\s*(.*?)(?:\s{2,})?$")


def build_prompt(description: str, exam_name: str) -> str:
    return (
        "Create a single clean square image for a Latvian A2 language exam. "
        "Show only the scene described, with everyday realistic details, natural lighting, "
        "clear human actions, no text, no watermark, no collage, and no extra panels. "
        "The image should be easy for students to describe in one sentence. "
        f"Scene: {description} "
        f"Exam set: {exam_name}."
    )


def parse_exam(md_path: Path) -> list[tuple[Path, str]]:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    results: list[tuple[Path, str]] = []

    for idx, line in enumerate(lines):
        write_match = WRITING_IMAGE_RE.search(line)
        if write_match and write_match.group(1).endswith("_1.png"):
            image_paths = []
            cursor = idx
            while cursor < len(lines):
                m = WRITING_IMAGE_RE.search(lines[cursor])
                if not m:
                    break
                image_paths.append(ROOT / "codex" / "Attachments" / Path(m.group(1)).relative_to("Attachments"))
                cursor += 1

            descriptions = []
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
            while cursor < len(lines) and len(descriptions) < len(image_paths):
                if not lines[cursor].strip():
                    cursor += 1
                    continue
                m = NUMBERED_DESC_RE.match(lines[cursor])
                if not m:
                    break
                descriptions.append(m.group(2).strip())
                cursor += 1

            if len(image_paths) != len(descriptions):
                raise ValueError(
                    f"{md_path}: expected {len(image_paths)} writing descriptions, found {len(descriptions)}"
                )
            results.extend(zip(image_paths, descriptions))

        speak_match = SPEAKING_IMAGE_RE.search(line)
        if speak_match and speak_match.group(1).endswith("_1.png"):
            image_a = ROOT / "codex" / "Attachments" / Path(speak_match.group(1)).relative_to("Attachments")
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            match_b = SPEAKING_IMAGE_RE.search(next_line)
            if not match_b:
                raise ValueError(f"{md_path}: missing second speaking image after line {idx + 1}")
            image_b = ROOT / "codex" / "Attachments" / Path(match_b.group(1)).relative_to("Attachments")

            descs: dict[str, str] = {}
            cursor = idx + 2
            while cursor < len(lines) and len(descs) < 2:
                m = SPEAKING_DESC_RE.match(lines[cursor].strip())
                if m:
                    descs[m.group(1)] = m.group(2).strip()
                cursor += 1

            if set(descs) != {"A", "B"}:
                raise ValueError(f"{md_path}: could not find both speaking descriptions")

            results.append((image_a, descs["A"]))
            results.append((image_b, descs["B"]))

    if not results:
        raise ValueError(f"{md_path}: no image mappings found")
    return results


def generate_image(prompt: str) -> bytes:
    payload = json.dumps(
        {
            "model": MODEL,
            "prompt": prompt,
            "size": GENERATE_SIZE,
            "response_format": "b64_json",
            "n": 1,
            "quality": "low",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        data = json.load(response)
    try:
        image_b64 = data["data"][0]["b64_json"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Ollama response shape: {data}") from exc
    return base64.b64decode(image_b64)


def write_image(target: Path, image_bytes: bytes) -> None:
    tmp = target.with_suffix(".tmp.png")
    tmp.write_bytes(image_bytes)
    subprocess.run(
        ["sips", "-z", str(UPSCALE_SIZE), str(UPSCALE_SIZE), str(tmp)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tmp.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exam",
        action="append",
        help="Exam markdown filename to process, e.g. A2_Mock_Exam_01.md. Can be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print mappings without generating images.")
    args = parser.parse_args()

    md_paths = (
        [CODEX_DIR / exam for exam in args.exam]
        if args.exam
        else sorted(CODEX_DIR.glob("A2_Mock_Exam_*.md"))
    )

    all_items: list[tuple[Path, str, str]] = []
    for md_path in md_paths:
        exam_name = md_path.stem
        for image_path, description in parse_exam(md_path):
            all_items.append((image_path, description, exam_name))

    for image_path, description, exam_name in all_items:
        print(f"{exam_name}: {image_path.relative_to(ROOT)} <- {description}", flush=True)
        if args.dry_run:
            continue
        prompt = build_prompt(description, exam_name)
        try:
            image_bytes = generate_image(prompt)
        except urllib.error.URLError as exc:
            print(f"Failed to call Ollama for {image_path}: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Failed to generate {image_path}: {exc}", file=sys.stderr)
            return 1
        write_image(image_path, image_bytes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
