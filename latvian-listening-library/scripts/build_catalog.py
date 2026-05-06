#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

LIBRARY_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = LIBRARY_ROOT / "web"
PROGRESS_PATH = LIBRARY_ROOT / "state" / "progress.json"
CATALOG_PATH = WEB_DIR / "catalog.json"
WEB_DATA_LINK = WEB_DIR / "data"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def rel_from_web(path_text: str) -> str:
    if path_text.startswith("data/"):
        return quote(path_text, safe="/")
    path = LIBRARY_ROOT / path_text
    try:
        return quote(path.relative_to(LIBRARY_ROOT).as_posix(), safe="/")
    except ValueError:
        return quote(path_text, safe="/")


def ensure_web_data_link() -> None:
    target = Path("..") / "data"
    if WEB_DATA_LINK.is_symlink():
        if WEB_DATA_LINK.readlink() != target:
            WEB_DATA_LINK.unlink()
            WEB_DATA_LINK.symlink_to(target, target_is_directory=True)
        return
    if WEB_DATA_LINK.exists():
        return
    WEB_DATA_LINK.symlink_to(target, target_is_directory=True)


def extract_body(markdown_path: Path, heading: str) -> str:
    if not markdown_path.exists():
        return ""
    text = markdown_path.read_text(encoding="utf-8")
    marker = f"## {heading}"
    if marker not in text:
        return ""
    body = text.split(marker, 1)[1]
    if "\n## " in body:
        body = body.split("\n## ", 1)[0]
    return body.strip()


def lesson_group(title: str) -> str | None:
    match = re.match(r"^(\d+)(?:[._-]|$)", title)
    if match:
        return f"{int(match.group(1))}. nodaļa"
    return None


def status_for(item: dict[str, Any]) -> str:
    if item.get("overall_status") == "completed":
        return "completed"
    if item.get("transcription_status") == "transcribed" and item.get("translation_status") != "translated":
        return "transcribed only"
    if item.get("translation_status") == "failed":
        return "translation failed"
    if item.get("overall_status") == "failed":
        return "failed"
    return item.get("overall_status") or "discovered"


def sort_key(item: dict[str, Any]) -> tuple[str, list[tuple[int, int | str]]]:
    title = item.get("title", "")
    pieces: list[tuple[int, int | str]] = []
    for part in re.split(r"(\d+)", title):
        if not part:
            continue
        pieces.append((0, int(part)) if part.isdigit() else (1, part.lower()))
    return item.get("level", ""), pieces


def main() -> int:
    ensure_web_data_link()
    progress = read_json(PROGRESS_PATH, {"items": {}})
    catalog: list[dict[str, Any]] = []
    for item in progress.get("items", {}).values():
        lv_path = LIBRARY_ROOT / item.get("lv_markdown_path", "")
        en_path = LIBRARY_ROOT / item.get("en_markdown_path", "")
        audio_path = item.get("copied_audio_path", "")
        title = Path(item.get("original_file_path", item.get("source", "audio"))).stem
        catalog.append(
            {
                "id": item.get("id"),
                "level": item.get("level"),
                "title": title,
                "original_filename": Path(item.get("original_file_path", "")).name,
                "audio_url": rel_from_web(audio_path) if audio_path else "",
                "lv_text": extract_body(lv_path, "Latvian Transcript"),
                "en_text": extract_body(en_path, "English Translation"),
                "lv_markdown_url": rel_from_web(item.get("lv_markdown_path", "")) if item.get("lv_markdown_path") else "",
                "en_markdown_url": rel_from_web(item.get("en_markdown_path", "")) if item.get("en_markdown_path") else "",
                "status": status_for(item),
                "transcription_status": item.get("transcription_status"),
                "translation_status": item.get("translation_status"),
                "lesson_group": lesson_group(title),
                "order": 0,
            }
        )
    catalog.sort(key=sort_key)
    for index, item in enumerate(catalog, start=1):
        item["order"] = index
    atomic_write_text(CATALOG_PATH, json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {CATALOG_PATH} with {len(catalog)} item(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
