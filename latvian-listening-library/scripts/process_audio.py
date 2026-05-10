#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from groq import Groq
from groq import APIConnectionError, APIError, AuthenticationError, RateLimitError
from mutagen import File as MutagenFile
from tqdm import tqdm

TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
DEFAULT_LIBRETRANSLATE_URL = "http://localhost:5000"
MAX_RETRIES = 3
CHUNK_SIZE = 3500

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = LIBRARY_ROOT / "state"
LOG_DIR = LIBRARY_ROOT / "logs"
PROGRESS_PATH = STATE_DIR / "progress.json"
FAILED_PATH = STATE_DIR / "failed_items.json"
LOG_PATH = LOG_DIR / "processing.log"


@dataclass(frozen=True)
class SourceAudio:
    level: str
    source_path: Path
    title: str
    sha256: str
    item_id: str


class BlockingProcessingError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_suffix(path.suffix + f".corrupt.{int(time.time())}")
        shutil.copy2(path, backup)
        logging.error("Invalid JSON at %s; backed up to %s", path, backup)
        return default


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slug(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return safe or "audio"


def relative(path: Path) -> str:
    try:
        return path.relative_to(LIBRARY_ROOT).as_posix()
    except ValueError:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path.as_posix()


def source_candidates(level: str) -> list[Path]:
    folder = f"{level}_klausisanas"
    return [PROJECT_ROOT / folder, PROJECT_ROOT / "codex" / folder]


def path_hash(path: Path) -> str:
    return hashlib.sha1(relative(path).encode("utf-8")).hexdigest()[:8]


def discover_sources(level_filter: str | None = None, existing_items: dict[str, Any] | None = None) -> list[SourceAudio]:
    levels = [level_filter] if level_filter else ["A1", "A2"]
    raw: list[tuple[str, Path, str, str]] = []
    seen: set[Path] = set()
    for level in levels:
        for root in source_candidates(level):
            if not root.exists():
                continue
            for source_path in sorted(root.rglob("*.mp3")):
                real = source_path.resolve()
                if real in seen:
                    continue
                seen.add(real)
                digest = sha256_file(source_path)
                base = source_path.stem
                raw.append((level, source_path, base, digest))
    grouped: dict[tuple[str, str], list[Path]] = {}
    for level, source_path, _base, digest in raw:
        grouped.setdefault((level, digest), []).append(source_path)

    discovered: list[SourceAudio] = []
    existing_items = existing_items or {}
    for level, source_path, base, digest in raw:
        legacy_id = f"{level}-{digest[:16]}"
        group = grouped[(level, digest)]
        item_id = legacy_id
        if len(group) > 1:
            existing = existing_items.get(legacy_id, {})
            existing_source = existing.get("source") or existing.get("original_file_path")
            if existing_source:
                item_id = legacy_id if existing_source == relative(source_path) else f"{legacy_id}-{path_hash(source_path)}"
            elif source_path != group[0]:
                item_id = f"{legacy_id}-{path_hash(source_path)}"
        discovered.append(SourceAudio(level, source_path, base, digest, item_id))
    return discovered


def load_groq_api_key() -> str | None:
    load_dotenv(PROJECT_ROOT / ".env")
    for name in ("GROQ_API_KEY", "GROQ_API_TOKEN", "GROQ_KEY"):
        value = os.getenv(name)
        if value:
            return value
    return None


def output_paths(item: SourceAudio) -> dict[str, Path]:
    level_dir = LIBRARY_ROOT / "data" / f"{item.level}_klausisanas"
    filename = item.source_path.name
    base = slug(item.source_path.stem)
    return {
        "audio": level_dir / "audio" / filename,
        "lv": level_dir / "transcripts_lv" / f"{base}.lv.md",
        "en": level_dir / "translations_en" / f"{base}.en.md",
        "metadata": level_dir / "metadata" / f"{base}.json",
    }


def duration_seconds(path: Path) -> float | None:
    try:
        audio = MutagenFile(path)
        if audio and audio.info and getattr(audio.info, "length", None):
            return round(float(audio.info.length), 3)
    except Exception as exc:
        logging.warning("Could not detect duration for %s: %s", path, exc)
    return None


def progress_item(item: SourceAudio, paths: dict[str, Path], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    now = utc_now()
    data = dict(existing or {})
    data.update(
        {
            "id": item.item_id,
            "level": item.level,
            "source": relative(item.source_path),
            "original_file_path": relative(item.source_path),
            "copied_audio_path": relative(paths["audio"]),
            "lv_markdown_path": relative(paths["lv"]),
            "en_markdown_path": relative(paths["en"]),
            "metadata_path": relative(paths["metadata"]),
            "file_size_bytes": item.source_path.stat().st_size,
            "sha256": item.sha256,
            "updated_at": now,
        }
    )
    data.setdefault("created_at", now)
    data.setdefault("audio_copied", False)
    data.setdefault("transcription_status", "discovered")
    data.setdefault("translation_status", "discovered")
    data.setdefault("overall_status", "discovered")
    data.setdefault("attempts", 0)
    data.setdefault("transcription_attempts", 0)
    data.setdefault("translation_attempts", 0)
    data.setdefault("last_error", None)
    data.setdefault("last_transcription_error", None)
    data.setdefault("last_translation_error", None)
    return data


def save_progress(progress: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = utc_now()
    atomic_write_json(PROGRESS_PATH, progress)


def save_failed(failed: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(FAILED_PATH, failed)


def update_metadata(item_data: dict[str, Any], paths: dict[str, Path], transcript: str = "", translation: str = "") -> None:
    meta = {
        "id": item_data["id"],
        "level": item_data["level"],
        "original_file_path": item_data["original_file_path"],
        "copied_audio_path": item_data["copied_audio_path"],
        "lv_markdown_path": item_data["lv_markdown_path"],
        "en_markdown_path": item_data["en_markdown_path"],
        "file_size_bytes": item_data["file_size_bytes"],
        "sha256": item_data["sha256"],
        "transcription_provider": "Groq",
        "transcription_model": TRANSCRIPTION_MODEL,
        "translation_provider": "Local LibreTranslate",
        "translation_engine": "LibreTranslate",
        "translation_source_language": "lv",
        "translation_target_language": "en",
        "translation_endpoint": item_data.get("translation_endpoint", DEFAULT_LIBRETRANSLATE_URL),
        "transcription_status": item_data.get("transcription_status"),
        "translation_status": item_data.get("translation_status"),
        "attempts": item_data.get("attempts", 0),
        "transcription_attempts": item_data.get("transcription_attempts", 0),
        "translation_attempts": item_data.get("translation_attempts", 0),
        "last_error": item_data.get("last_error"),
        "last_transcription_error": item_data.get("last_transcription_error"),
        "last_translation_error": item_data.get("last_translation_error"),
        "created_at": item_data.get("created_at"),
        "updated_at": item_data.get("updated_at"),
        "duration_seconds": item_data.get("duration_seconds"),
        "transcript_preview": transcript[:240],
        "translation_preview": translation[:240],
    }
    atomic_write_json(paths["metadata"], meta)


def markdown(title: str, level: str, audio_path: str, heading: str, body: str, metadata_lines: list[str]) -> str:
    lines = [
        f"# {title}",
        "",
        "## Level",
        level,
        "",
        "## Source Audio",
        audio_path,
        "",
        f"## {heading}",
        "",
        body.strip(),
        "",
        "## Metadata",
        *metadata_lines,
        "",
    ]
    return "\n".join(lines)


def extract_body(markdown_text: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in markdown_text:
        return ""
    after = markdown_text.split(marker, 1)[1]
    if "\n## " in after:
        after = after.split("\n## ", 1)[0]
    return after.strip()


def find_completed_same_audio(item: SourceAudio, progress: dict[str, Any]) -> dict[str, Any] | None:
    for existing in progress.get("items", {}).values():
        if existing.get("id") == item.item_id:
            continue
        if existing.get("level") != item.level or existing.get("sha256") != item.sha256:
            continue
        if existing.get("transcription_status") == "transcribed" and existing.get("translation_status") == "translated":
            lv_path = LIBRARY_ROOT / existing.get("lv_markdown_path", "")
            en_path = LIBRARY_ROOT / existing.get("en_markdown_path", "")
            if lv_path.exists() and en_path.exists():
                return existing
    return None


def retry(operation_name: str, callback):
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return callback()
        except (RateLimitError, APIConnectionError, requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            wait = 2 ** (attempt - 1)
            logging.warning("%s retryable failure %s/%s: %s", operation_name, attempt, MAX_RETRIES, exc)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def transcribe_with_groq(client: Groq, audio_path: Path) -> str:
    def call():
        with audio_path.open("rb") as audio:
            return client.audio.transcriptions.create(
                file=(audio_path.name, audio),
                model=TRANSCRIPTION_MODEL,
                language="lv",
                temperature=0,
                response_format="verbose_json",
            )

    response = retry("Groq transcription", call)
    text = getattr(response, "text", None) or (response.get("text") if isinstance(response, dict) else None)
    if not text or not text.strip():
        raise RuntimeError("Groq returned an empty or partial transcription output.")
    return text.strip()


def check_libretranslate(base_url: str) -> None:
    base_url = base_url.rstrip("/")
    try:
        response = requests.get(f"{base_url}/languages", timeout=10)
        response.raise_for_status()
        languages = response.json()
    except requests.RequestException as exc:
        raise BlockingProcessingError(f"LibreTranslate is not ready at {base_url}: {exc}") from exc
    except ValueError as exc:
        raise BlockingProcessingError(f"LibreTranslate /languages returned invalid JSON: {exc}") from exc
    codes = {item.get("code") for item in languages if isinstance(item, dict)}
    if "lv" not in codes:
        raise BlockingProcessingError('LibreTranslate language "lv" is not available.')
    if "en" not in codes:
        raise BlockingProcessingError('LibreTranslate language "en" is not available.')
    lv_entry = next((item for item in languages if item.get("code") == "lv"), {})
    targets = set(lv_entry.get("targets") or [])
    if targets and "en" not in targets:
        raise BlockingProcessingError("LibreTranslate does not report lv -> en support.")


def split_text(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [text.strip()]:
        if len(paragraph) > max_chars:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        else:
            sentences = [paragraph]
        for sentence in sentences:
            candidate = f"{current}\n\n{sentence}".strip() if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def translate_text(text: str, base_url: str) -> str:
    base_url = base_url.rstrip("/")
    translated_chunks: list[str] = []
    for chunk in split_text(text):
        def call():
            response = requests.post(
                f"{base_url}/translate",
                json={"q": chunk, "source": "lv", "target": "en", "format": "text"},
                timeout=90,
            )
            response.raise_for_status()
            return response

        response = retry("LibreTranslate translation", call)
        try:
            translated = response.json().get("translatedText", "").strip()
        except ValueError as exc:
            raise RuntimeError(f"LibreTranslate returned invalid JSON: {exc}") from exc
        if not translated:
            raise RuntimeError("LibreTranslate returned an empty translation output.")
        translated_chunks.append(translated)
    return "\n\n".join(translated_chunks).strip()


def copy_audio(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256_file(target) == sha256_file(source):
        return
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    shutil.copy2(source, tmp)
    os.replace(tmp, target)


def process_item(
    item: SourceAudio,
    item_data: dict[str, Any],
    paths: dict[str, Path],
    progress: dict[str, Any],
    failed: dict[str, Any],
    args: argparse.Namespace,
    groq_client: Groq | None,
) -> None:
    item_data["attempts"] = item_data.get("attempts", 0) + 1
    item_data["translation_endpoint"] = args.libretranslate_url
    item_data["duration_seconds"] = duration_seconds(item.source_path)

    if args.skip_existing and paths["lv"].exists() and paths["en"].exists() and not args.force:
        item_data.update({"overall_status": "skipped", "last_error": None, "updated_at": utc_now()})
        progress["items"][item.item_id] = item_data
        save_progress(progress)
        return

    if args.dry_run:
        logging.info("DRY RUN would process %s -> %s", relative(item.source_path), relative(paths["audio"]))
        return

    try:
        if not item_data.get("audio_copied") or not paths["audio"].exists() or args.force:
            item_data["overall_status"] = "copied"
            copy_audio(item.source_path, paths["audio"])
            item_data["audio_copied"] = True
            item_data["updated_at"] = utc_now()
            progress["items"][item.item_id] = item_data
            save_progress(progress)

        reusable = None if args.force else find_completed_same_audio(item, progress)
        if reusable and not paths["lv"].exists() and not args.translate_only:
            source_lv = (LIBRARY_ROOT / reusable["lv_markdown_path"]).read_text(encoding="utf-8")
            transcript = extract_body(source_lv, "Latvian Transcript")
            lv_md = markdown(
                item.source_path.name,
                item.level,
                relative(paths["audio"]),
                "Latvian Transcript",
                transcript,
                [
                    f"- Source file: {relative(item.source_path)}",
                    f"- Generated at: {utc_now()}",
                    "- Transcription provider: Groq",
                    f"- Transcription model: {TRANSCRIPTION_MODEL}",
                    "- Language: lv",
                    f"- Reused from identical audio SHA-256 item: {reusable['id']}",
                ],
            )
            atomic_write_text(paths["lv"], lv_md)
            item_data.update({"transcription_status": "transcribed", "last_transcription_error": None})
            progress["items"][item.item_id] = item_data
            save_progress(progress)

        if reusable and not paths["en"].exists() and not args.transcribe_only:
            source_en = (LIBRARY_ROOT / reusable["en_markdown_path"]).read_text(encoding="utf-8")
            translation = extract_body(source_en, "English Translation")
            en_md = markdown(
                item.source_path.name,
                item.level,
                relative(paths["audio"]),
                "English Translation",
                translation,
                [
                    f"- Source file: {relative(item.source_path)}",
                    f"- Generated at: {utc_now()}",
                    "- Translation provider: Local LibreTranslate",
                    "- Translation source language: lv",
                    "- Translation target language: en",
                    f"- Translation endpoint: {args.libretranslate_url.rstrip('/')}",
                    f"- Reused from identical audio SHA-256 item: {reusable['id']}",
                ],
            )
            atomic_write_text(paths["en"], en_md)
            item_data.update({"translation_status": "translated", "last_translation_error": None})
            item_data.update({"overall_status": "completed", "last_error": None, "updated_at": utc_now()})
            progress["items"][item.item_id] = item_data
            update_metadata(item_data, paths, transcript, translation)
            save_progress(progress)
            failed.pop(item.item_id, None)
            save_failed(failed)
            return

        transcript = ""
        if paths["lv"].exists() and not args.force:
            transcript = extract_body(paths["lv"].read_text(encoding="utf-8"), "Latvian Transcript")

        if not args.translate_only and (args.force or not paths["lv"].exists() or item_data.get("transcription_status") != "transcribed"):
            if groq_client is None:
                raise BlockingProcessingError("Missing Groq API key; transcription is required.")
            item_data["transcription_status"] = "transcribing"
            item_data["updated_at"] = utc_now()
            progress["items"][item.item_id] = item_data
            save_progress(progress)
            item_data["transcription_attempts"] = item_data.get("transcription_attempts", 0) + 1
            transcript = transcribe_with_groq(groq_client, paths["audio"])
            lv_md = markdown(
                item.source_path.name,
                item.level,
                relative(paths["audio"]),
                "Latvian Transcript",
                transcript,
                [
                    f"- Source file: {relative(item.source_path)}",
                    f"- Generated at: {utc_now()}",
                    "- Transcription provider: Groq",
                    f"- Transcription model: {TRANSCRIPTION_MODEL}",
                    "- Language: lv",
                ],
            )
            atomic_write_text(paths["lv"], lv_md)
            item_data.update({"transcription_status": "transcribed", "last_transcription_error": None})
            progress["items"][item.item_id] = item_data
            save_progress(progress)

        if args.transcribe_only:
            item_data["overall_status"] = "transcribed"
            item_data["updated_at"] = utc_now()
            progress["items"][item.item_id] = item_data
            update_metadata(item_data, paths, transcript, "")
            save_progress(progress)
            return

        if not transcript and paths["lv"].exists():
            transcript = extract_body(paths["lv"].read_text(encoding="utf-8"), "Latvian Transcript")
        if not transcript:
            raise RuntimeError("No Latvian transcript text is available for translation.")

        translation = ""
        if paths["en"].exists() and not args.force:
            translation = extract_body(paths["en"].read_text(encoding="utf-8"), "English Translation")

        if args.force or not paths["en"].exists() or item_data.get("translation_status") != "translated":
            item_data["translation_status"] = "translating"
            item_data["updated_at"] = utc_now()
            progress["items"][item.item_id] = item_data
            save_progress(progress)
            item_data["translation_attempts"] = item_data.get("translation_attempts", 0) + 1
            translation = translate_text(transcript, args.libretranslate_url)
            en_md = markdown(
                item.source_path.name,
                item.level,
                relative(paths["audio"]),
                "English Translation",
                translation,
                [
                    f"- Source file: {relative(item.source_path)}",
                    f"- Generated at: {utc_now()}",
                    "- Translation provider: Local LibreTranslate",
                    "- Translation source language: lv",
                    "- Translation target language: en",
                    f"- Translation endpoint: {args.libretranslate_url.rstrip('/')}",
                ],
            )
            atomic_write_text(paths["en"], en_md)
            item_data.update({"translation_status": "translated", "last_translation_error": None})

        item_data.update({"overall_status": "completed", "last_error": None, "updated_at": utc_now()})
        progress["items"][item.item_id] = item_data
        update_metadata(item_data, paths, transcript, translation)
        save_progress(progress)
        failed.pop(item.item_id, None)
        save_failed(failed)
    except (AuthenticationError, RateLimitError, APIError, APIConnectionError, requests.RequestException, RuntimeError) as exc:
        message = str(exc)
        if isinstance(exc, AuthenticationError):
            message = "Groq authentication failed. Check the key in .env."
        elif isinstance(exc, RateLimitError):
            message = "Groq rate limit or quota/credit issue encountered."
        item_data["last_error"] = message
        if item_data.get("transcription_status") == "transcribing":
            item_data.update({"transcription_status": "failed", "last_transcription_error": message})
        elif item_data.get("translation_status") == "translating":
            item_data.update({"translation_status": "failed", "last_translation_error": message})
        item_data["overall_status"] = "failed"
        item_data["updated_at"] = utc_now()
        progress["items"][item.item_id] = item_data
        failed[item.item_id] = {"id": item.item_id, "source": relative(item.source_path), "error": message, "updated_at": utc_now()}
        save_progress(progress)
        save_failed(failed)
        logging.error("Failed %s: %s", item.source_path, message)
        if isinstance(exc, (AuthenticationError, RateLimitError)):
            raise BlockingProcessingError(message) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe Latvian MP3s with Groq and translate with local LibreTranslate.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--level", choices=["A1", "A2"])
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--transcribe-only", action="store_true")
    parser.add_argument("--translate-only", action="store_true")
    parser.add_argument("--check-libretranslate", action="store_true")
    parser.add_argument("--libretranslate-url", default=DEFAULT_LIBRETRANSLATE_URL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging()
    if args.transcribe_only and args.translate_only:
        raise SystemExit("--transcribe-only and --translate-only cannot be combined.")

    progress = load_json(PROGRESS_PATH, {"items": {}, "created_at": utc_now(), "updated_at": utc_now()})
    failed = load_json(FAILED_PATH, {})
    sources = discover_sources(args.level, progress.get("items", {}))
    if args.limit:
        sources = sources[: args.limit]
    logging.info("Discovered %s MP3 file(s).", len(sources))

    needs_translation = not args.transcribe_only
    needs_transcription = not args.translate_only
    groq_client: Groq | None = None

    if needs_translation and (args.check_libretranslate or not args.dry_run):
        try:
            check_libretranslate(args.libretranslate_url)
            logging.info("LibreTranslate is ready at %s", args.libretranslate_url)
        except BlockingProcessingError as exc:
            logging.error("%s", exc)
            print(f"Cannot translate yet: {exc}")
            return 2

    if needs_transcription and not args.dry_run:
        api_key = load_groq_api_key()
        if not api_key:
            logging.error("Missing Groq API key in .env; checked GROQ_API_KEY, GROQ_API_TOKEN, GROQ_KEY.")
            print("Missing Groq API key in .env. Add GROQ_API_KEY, GROQ_API_TOKEN, or GROQ_KEY and rerun with --resume.")
            return 2
        groq_client = Groq(api_key=api_key)

    for item in tqdm(sources, disable=args.dry_run):
        paths = output_paths(item)
        existing = progress.get("items", {}).get(item.item_id)
        item_data = progress_item(item, paths, existing)
        if not args.force and item_data.get("overall_status") == "completed" and paths["lv"].exists() and paths["en"].exists():
            continue
        try:
            process_item(item, item_data, paths, progress, failed, args, groq_client)
        except BlockingProcessingError as exc:
            logging.error("Blocking error; stopping safely: %s", exc)
            print(f"Stopped safely: {exc}. Resume later with --resume.")
            return 2

    save_progress(progress)
    save_failed(failed)
    completed = sum(1 for item in progress.get("items", {}).values() if item.get("overall_status") == "completed")
    transcribed_only = sum(
        1
        for item in progress.get("items", {}).values()
        if item.get("transcription_status") == "transcribed" and item.get("translation_status") != "translated"
    )
    logging.info("Summary: discovered=%s completed=%s transcribed_only=%s failed=%s", len(sources), completed, transcribed_only, len(failed))
    print(f"Discovered: {len(sources)} | Completed: {completed} | Transcribed only: {transcribed_only} | Failed: {len(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
