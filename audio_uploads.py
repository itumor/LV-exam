"""Speaking-section audio upload store.

T-018 deliverable. Provides a thread-safe ``AudioUploadStore`` that persists
learner-recorded audio (one file per attempt+task) under a user-scoped
directory tree. Enforces a per-file size cap and a MIME-type allowlist, and
guards against path-traversal in the caller-supplied ``attempt_id``/``task_id``
values.

This module is intentionally standalone (no import from ``server.py``) so the
server monolith stays slim and so the store can be unit-tested without
spinning up the HTTP server.

Layout on disk::

    <base_dir>/<user_id>/<attempt_id>/<task_id>.<ext>

Public surface:

* ``AudioUploadStore(base_dir, max_bytes=20_000_000, allowed_mimes=...)``
* ``store.save(attempt_id, task_id, user_id, content_type, stream) -> str``
* ``store.load(attempt_id, task_id, user_id) -> (mime, bytes)``
* ``store.delete(attempt_id, task_id, user_id) -> bool``
* ``store.delete_attempt(attempt_id, user_id) -> int``  (cleanup helper)

All caller-supplied identifiers are validated against a strict pattern; any
identifier containing path separators, ``..``, NUL bytes, or characters
outside ``[A-Za-z0-9_.-]`` is rejected with ``UnsafeIdentifierError``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from pathlib import Path
from typing import BinaryIO, Iterable

__all__ = [
    "AudioUploadStore",
    "AudioUploadError",
    "OversizeUploadError",
    "UnsupportedMimeError",
    "UnsafeIdentifierError",
    "UploadNotFoundError",
    "AttemptUploadLimitError",
]


# ----- Errors -----------------------------------------------------------------


class AudioUploadError(Exception):
    """Base class for audio-upload errors."""


class OversizeUploadError(AudioUploadError):
    """Raised when an upload exceeds the configured ``max_bytes``."""


class UnsupportedMimeError(AudioUploadError):
    """Raised when the caller-supplied content type is not allowed."""


class UnsafeIdentifierError(AudioUploadError):
    """Raised when a caller-supplied id would escape the storage root."""


class UploadNotFoundError(AudioUploadError):
    """Raised when ``load`` cannot find a stored upload."""


class AttemptUploadLimitError(AudioUploadError):
    """Raised when a single attempt exceeds the per-attempt file cap."""


# ----- Constants --------------------------------------------------------------

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")

_MIME_TO_EXT = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
}

_DEFAULT_ALLOWED_MIMES = (
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/mpeg",
)

_READ_CHUNK = 64 * 1024  # 64 KiB

# Per-attempt cap (T-018 spec: max 4 task uploads per attempt).
DEFAULT_MAX_TASKS_PER_ATTEMPT = 4


# ----- Helpers ---------------------------------------------------------------


def _validate_identifier(name: str, label: str) -> str:
    """Reject anything that could traverse out of the storage root."""

    if not isinstance(name, str):
        raise UnsafeIdentifierError(f"{label} must be a string")
    if not name:
        raise UnsafeIdentifierError(f"{label} is required")
    if "\x00" in name or "/" in name or "\\" in name:
        raise UnsafeIdentifierError(f"{label} contains forbidden separator")
    if name in {".", ".."}:
        raise UnsafeIdentifierError(f"{label} is a reserved name")
    if ".." in name:
        # extra safety belt: refuse any embedded parent indicator.
        raise UnsafeIdentifierError(f"{label} contains '..'")
    if not _ID_PATTERN.match(name):
        raise UnsafeIdentifierError(
            f"{label} must match [A-Za-z0-9][A-Za-z0-9_.-]{{0,127}}"
        )
    return name


def _normalize_mime(content_type: str) -> str:
    if not isinstance(content_type, str):
        raise UnsupportedMimeError("content_type must be a string")
    # Strip any '; codecs=...' suffix the browser may attach.
    head = content_type.split(";", 1)[0].strip().lower()
    return head


def _extension_for_mime(mime: str) -> str:
    return _MIME_TO_EXT.get(mime, "bin")


def _iter_chunks(stream: object) -> Iterable[bytes]:
    """Yield bytes from ``stream``.

    Accepts:
      * ``bytes`` / ``bytearray`` (returned in one chunk)
      * any object exposing ``read(size)`` returning ``bytes``
      * any iterable of ``bytes``
    """

    if isinstance(stream, (bytes, bytearray)):
        yield bytes(stream)
        return
    if hasattr(stream, "read"):
        read = stream.read  # type: ignore[attr-defined]
        while True:
            chunk = read(_READ_CHUNK)
            if not chunk:
                break
            if not isinstance(chunk, (bytes, bytearray)):
                raise AudioUploadError("stream.read() must return bytes")
            yield bytes(chunk)
        return
    # Last-ditch: iterable of bytes
    try:
        for chunk in stream:  # type: ignore[assignment]
            if not isinstance(chunk, (bytes, bytearray)):
                raise AudioUploadError("stream chunks must be bytes")
            yield bytes(chunk)
    except TypeError as error:
        raise AudioUploadError(
            "stream must be bytes, file-like, or iterable of bytes"
        ) from error


# ----- Store -----------------------------------------------------------------


class AudioUploadStore:
    """Thread-safe filesystem-backed store for speaking uploads."""

    def __init__(
        self,
        base_dir: os.PathLike[str] | str,
        max_bytes: int = 20_000_000,
        allowed_mimes: Iterable[str] = _DEFAULT_ALLOWED_MIMES,
        max_tasks_per_attempt: int = DEFAULT_MAX_TASKS_PER_ATTEMPT,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if max_tasks_per_attempt <= 0:
            raise ValueError("max_tasks_per_attempt must be positive")
        self.base_dir = Path(base_dir).resolve()
        self.max_bytes = int(max_bytes)
        self.allowed_mimes = frozenset(m.lower() for m in allowed_mimes)
        self.max_tasks_per_attempt = int(max_tasks_per_attempt)
        # One coarse lock — uploads are infrequent and small relative to
        # request latency, so a single lock keeps semantics simple.
        self._lock = threading.RLock()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ---- internal path helpers --------------------------------------------

    def _attempt_dir(self, user_id: str, attempt_id: str) -> Path:
        _validate_identifier(user_id, "user_id")
        _validate_identifier(attempt_id, "attempt_id")
        candidate = (self.base_dir / user_id / attempt_id).resolve()
        # Defence-in-depth: even with the regex guard, ensure the resolved
        # path stays under the configured base.
        try:
            candidate.relative_to(self.base_dir)
        except ValueError as error:
            raise UnsafeIdentifierError(
                "resolved attempt path escapes base_dir"
            ) from error
        return candidate

    def _file_path(
        self, user_id: str, attempt_id: str, task_id: str, ext: str
    ) -> Path:
        _validate_identifier(task_id, "task_id")
        return self._attempt_dir(user_id, attempt_id) / f"{task_id}.{ext}"

    def _find_existing(
        self, user_id: str, attempt_id: str, task_id: str
    ) -> Path | None:
        attempt_dir = self._attempt_dir(user_id, attempt_id)
        _validate_identifier(task_id, "task_id")
        if not attempt_dir.exists():
            return None
        for ext in set(_MIME_TO_EXT.values()):
            candidate = attempt_dir / f"{task_id}.{ext}"
            if candidate.exists():
                return candidate
        # Also accept .bin fallback or any extension matching task_id.<ext>
        for child in attempt_dir.iterdir():
            if child.is_file() and child.stem == task_id:
                return child
        return None

    # ---- public API --------------------------------------------------------

    def save(
        self,
        attempt_id: str,
        task_id: str,
        user_id: str,
        content_type: str,
        stream: BinaryIO | bytes | bytearray,
    ) -> str:
        """Persist an audio upload and return the relative path."""

        mime = _normalize_mime(content_type)
        if mime not in self.allowed_mimes:
            raise UnsupportedMimeError(f"content_type '{mime}' is not allowed")
        ext = _extension_for_mime(mime)

        with self._lock:
            attempt_dir = self._attempt_dir(user_id, attempt_id)
            attempt_dir.mkdir(parents=True, exist_ok=True)

            # Per-attempt cap: count existing distinct task files. If the task
            # already has a file, overwriting is allowed (retry flow).
            existing = self._find_existing(user_id, attempt_id, task_id)
            if existing is None:
                current_count = sum(
                    1
                    for child in attempt_dir.iterdir()
                    if child.is_file()
                    and not child.name.endswith(".meta.json")
                )
                if current_count >= self.max_tasks_per_attempt:
                    raise AttemptUploadLimitError(
                        f"attempt {attempt_id!r} already has "
                        f"{self.max_tasks_per_attempt} uploads"
                    )

            target = self._file_path(user_id, attempt_id, task_id, ext)
            tmp = target.with_suffix(target.suffix + ".part")

            total = 0
            try:
                with tmp.open("wb") as out:
                    for chunk in _iter_chunks(stream):
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise OversizeUploadError(
                                f"upload exceeds max_bytes={self.max_bytes}"
                            )
                        out.write(chunk)
                if total == 0:
                    raise AudioUploadError("upload is empty")
                # If a previous extension existed for the same task, remove it.
                if existing is not None and existing != target:
                    try:
                        existing.unlink()
                    except FileNotFoundError:
                        pass
                tmp.replace(target)
            except BaseException:
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass
                raise

            # Persist a small sidecar so the GET route can recover the mime
            # without re-sniffing the audio container.
            meta_path = target.with_suffix(target.suffix + ".meta.json")
            meta_path.write_text(
                json.dumps(
                    {"mime": mime, "bytes": total}, ensure_ascii=False
                ),
                encoding="utf-8",
            )

            return str(target.relative_to(self.base_dir))

    def load(
        self, attempt_id: str, task_id: str, user_id: str
    ) -> tuple[str, bytes]:
        """Return ``(mime, bytes)`` for a stored upload."""

        with self._lock:
            path = self._find_existing(user_id, attempt_id, task_id)
            if path is None:
                raise UploadNotFoundError(
                    f"no upload for {user_id}/{attempt_id}/{task_id}"
                )
            meta_path = path.with_suffix(path.suffix + ".meta.json")
            mime = "application/octet-stream"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    if isinstance(meta, dict) and isinstance(
                        meta.get("mime"), str
                    ):
                        mime = meta["mime"]
                except (OSError, ValueError):
                    pass
            else:
                # Best-effort fallback from the file extension.
                for candidate_mime, candidate_ext in _MIME_TO_EXT.items():
                    if path.suffix.lstrip(".") == candidate_ext:
                        mime = candidate_mime
                        break
            return mime, path.read_bytes()

    def delete(
        self, attempt_id: str, task_id: str, user_id: str
    ) -> bool:
        """Remove a single task upload. Returns ``True`` if a file was removed."""

        with self._lock:
            path = self._find_existing(user_id, attempt_id, task_id)
            if path is None:
                return False
            meta_path = path.with_suffix(path.suffix + ".meta.json")
            for candidate in (path, meta_path):
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    pass
            return True

    def delete_attempt(self, attempt_id: str, user_id: str) -> int:
        """Remove every audio file for the given attempt.

        Returns the count of files removed (excluding sidecar metadata).
        Used during attempt-expire/delete cleanup.
        """

        with self._lock:
            attempt_dir = self._attempt_dir(user_id, attempt_id)
            if not attempt_dir.exists():
                return 0
            removed = 0
            for child in attempt_dir.iterdir():
                if child.is_file() and not child.name.endswith(".meta.json"):
                    removed += 1
            try:
                shutil.rmtree(attempt_dir)
            except FileNotFoundError:
                pass
            # If the parent user dir is now empty, prune it to keep the tree tidy.
            parent = attempt_dir.parent
            try:
                if parent.exists() and parent != self.base_dir and not any(
                    parent.iterdir()
                ):
                    parent.rmdir()
            except OSError:
                pass
            return removed
