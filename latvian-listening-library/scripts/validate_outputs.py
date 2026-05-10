#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = LIBRARY_ROOT.parent


def source_roots(level: str) -> list[Path]:
    return [PROJECT_ROOT / f"{level}_klausisanas", PROJECT_ROOT / "codex" / f"{level}_klausisanas"]


def discover() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for level in ("A1", "A2"):
        for root in source_roots(level):
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.mp3")):
                real = path.resolve()
                if real not in seen:
                    seen.add(real)
                    files.append(path)
    return files


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def item_id_for(path: Path) -> str:
    level = "A1" if "A1_klausisanas" in path.parts else "A2"
    return f"{level}-{sha256_file(path)[:16]}"


def read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def body(path: Path, heading: str) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    marker = f"## {heading}"
    if marker not in text:
        return ""
    section = text.split(marker, 1)[1]
    if "\n## " in section:
        section = section.split("\n## ", 1)[0]
    return section.strip()


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    discovered = discover()

    progress_path = LIBRARY_ROOT / "state" / "progress.json"
    catalog_path = LIBRARY_ROOT / "web" / "catalog.json"
    failed_path = LIBRARY_ROOT / "state" / "failed_items.json"

    try:
        progress = read_json(progress_path)
    except Exception as exc:
        progress = {"items": {}}
        errors.append(f"progress.json is missing or invalid: {exc}")

    if catalog_path.exists():
        try:
            read_json(catalog_path)
        except Exception as exc:
            errors.append(f"catalog.json is invalid: {exc}")
    else:
        errors.append("web/catalog.json does not exist.")

    if failed_path.exists():
        try:
            failed = read_json(failed_path)
            if failed:
                warnings.append(f"{len(failed)} failed item(s) are recorded in state/failed_items.json.")
        except Exception as exc:
            errors.append(f"failed_items.json is invalid: {exc}")

    for relative in (
        "translation/check_libretranslate.py",
        "translation/docker-compose.yml",
        "translation/start_libretranslate.sh",
        "translation/stop_libretranslate.sh",
    ):
        if not (LIBRARY_ROOT / relative).exists():
            errors.append(f"Missing translation setup file: {relative}")

    progress_items = progress.get("items", {})
    progress_by_source = {
        item.get("source") or item.get("original_file_path"): item
        for item in progress_items.values()
    }
    missing_from_progress = 0
    for source in discovered:
        try:
            source_key = source.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            source_key = source.as_posix()
        item = progress_by_source.get(source_key)
        if not item:
            missing_from_progress += 1
            continue
        audio = LIBRARY_ROOT / item.get("copied_audio_path", "")
        if not audio.exists():
            errors.append(f"Discovered MP3 has no copied audio file: {source}")
    if missing_from_progress:
        errors.append(f"{missing_from_progress} discovered MP3 file(s) are not represented in progress.json.")

    for item in progress_items.values():
        audio = LIBRARY_ROOT / item.get("copied_audio_path", "")
        lv = LIBRARY_ROOT / item.get("lv_markdown_path", "")
        en = LIBRARY_ROOT / item.get("en_markdown_path", "")
        if item.get("audio_copied") and not audio.exists():
            errors.append(f"Copied audio missing for {item.get('id')}: {audio}")
        if item.get("transcription_status") == "transcribed":
            if not lv.exists() or not lv.read_text(encoding="utf-8").strip():
                errors.append(f"Latvian markdown missing or empty for {item.get('id')}")
        if item.get("overall_status") == "completed":
            if not en.exists() or not en.read_text(encoding="utf-8").strip():
                errors.append(f"English markdown missing or empty for completed item {item.get('id')}")
            lv_body = body(lv, "Latvian Transcript")
            en_body = body(en, "English Translation")
            if lv_body and en_body and lv_body == en_body:
                warnings.append(f"Translation text is identical to Latvian transcript for {item.get('id')}; verify manually.")

    print(f"Discovered MP3 files: {len(discovered)}")
    print(f"Progress items: {len(progress.get('items', {}))}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
