"""Unit tests for the T-018 AudioUploadStore."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from audio_uploads import (
    AttemptUploadLimitError,
    AudioUploadStore,
    OversizeUploadError,
    UnsafeIdentifierError,
    UnsupportedMimeError,
    UploadNotFoundError,
)


class AudioUploadStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.store = AudioUploadStore(
            base_dir=self.base,
            max_bytes=4096,
            allowed_mimes=("audio/webm", "audio/ogg", "audio/wav", "audio/mpeg"),
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ---- save -------------------------------------------------------------

    def test_save_writes_file_under_user_attempt_dir(self) -> None:
        rel = self.store.save(
            attempt_id="att1",
            task_id="task1",
            user_id="user_a",
            content_type="audio/webm",
            stream=b"hello-audio",
        )
        self.assertEqual(rel, "user_a/att1/task1.webm")
        target = self.base / "user_a" / "att1" / "task1.webm"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), b"hello-audio")

    def test_save_accepts_file_like_stream(self) -> None:
        rel = self.store.save(
            attempt_id="att1",
            task_id="task1",
            user_id="user_a",
            content_type="audio/ogg",
            stream=io.BytesIO(b"og-data"),
        )
        self.assertTrue(rel.endswith(".ogg"))

    def test_save_strips_codec_suffix_from_mime(self) -> None:
        rel = self.store.save(
            attempt_id="att1",
            task_id="task1",
            user_id="user_a",
            content_type="audio/webm; codecs=opus",
            stream=b"x",
        )
        self.assertTrue(rel.endswith(".webm"))

    def test_save_rejects_unknown_mime(self) -> None:
        with self.assertRaises(UnsupportedMimeError):
            self.store.save(
                attempt_id="att1",
                task_id="task1",
                user_id="user_a",
                content_type="video/mp4",
                stream=b"x",
            )

    def test_save_rejects_oversize_payload(self) -> None:
        with self.assertRaises(OversizeUploadError):
            self.store.save(
                attempt_id="att1",
                task_id="task1",
                user_id="user_a",
                content_type="audio/webm",
                stream=b"x" * 5000,
            )
        # The partial file must not survive.
        self.assertFalse((self.base / "user_a" / "att1" / "task1.webm").exists())
        self.assertFalse((self.base / "user_a" / "att1" / "task1.webm.part").exists())

    def test_save_rejects_empty_payload(self) -> None:
        with self.assertRaises(Exception):
            self.store.save(
                attempt_id="att1",
                task_id="task1",
                user_id="user_a",
                content_type="audio/webm",
                stream=b"",
            )

    def test_save_rejects_path_traversal_attempt_id(self) -> None:
        with self.assertRaises(UnsafeIdentifierError):
            self.store.save(
                attempt_id="../escape",
                task_id="task1",
                user_id="user_a",
                content_type="audio/webm",
                stream=b"x",
            )

    def test_save_rejects_path_traversal_task_id(self) -> None:
        with self.assertRaises(UnsafeIdentifierError):
            self.store.save(
                attempt_id="att1",
                task_id="../task",
                user_id="user_a",
                content_type="audio/webm",
                stream=b"x",
            )

    def test_save_rejects_separator_in_user_id(self) -> None:
        with self.assertRaises(UnsafeIdentifierError):
            self.store.save(
                attempt_id="att1",
                task_id="task1",
                user_id="user/a",
                content_type="audio/webm",
                stream=b"x",
            )

    def test_save_rejects_dot_only_identifier(self) -> None:
        for bad in (".", "..", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(UnsafeIdentifierError):
                    self.store.save(
                        attempt_id=bad,
                        task_id="task1",
                        user_id="user_a",
                        content_type="audio/webm",
                        stream=b"x",
                    )

    def test_save_respects_per_attempt_task_cap(self) -> None:
        store = AudioUploadStore(
            base_dir=self.base / "capped",
            max_bytes=4096,
            max_tasks_per_attempt=2,
        )
        store.save("att1", "task1", "u", "audio/webm", b"a")
        store.save("att1", "task2", "u", "audio/webm", b"b")
        with self.assertRaises(AttemptUploadLimitError):
            store.save("att1", "task3", "u", "audio/webm", b"c")
        # Re-uploading an existing task must succeed (retry flow).
        store.save("att1", "task1", "u", "audio/webm", b"retry")

    # ---- load -------------------------------------------------------------

    def test_load_returns_mime_and_bytes(self) -> None:
        self.store.save("att1", "task1", "user_a", "audio/webm", b"payload")
        mime, body = self.store.load("att1", "task1", "user_a")
        self.assertEqual(mime, "audio/webm")
        self.assertEqual(body, b"payload")

    def test_load_missing_raises_not_found(self) -> None:
        with self.assertRaises(UploadNotFoundError):
            self.store.load("att1", "task1", "user_a")

    def test_load_isolates_users(self) -> None:
        self.store.save("att1", "task1", "user_a", "audio/webm", b"alpha")
        self.store.save("att1", "task1", "user_b", "audio/ogg", b"beta")

        mime_a, body_a = self.store.load("att1", "task1", "user_a")
        mime_b, body_b = self.store.load("att1", "task1", "user_b")

        self.assertEqual(body_a, b"alpha")
        self.assertEqual(body_b, b"beta")
        self.assertEqual(mime_a, "audio/webm")
        self.assertEqual(mime_b, "audio/ogg")

        with self.assertRaises(UploadNotFoundError):
            self.store.load("att1", "task2", "user_a")

    def test_load_rejects_traversal(self) -> None:
        with self.assertRaises(UnsafeIdentifierError):
            self.store.load("../att", "task1", "user_a")

    # ---- delete -----------------------------------------------------------

    def test_delete_removes_file_and_sidecar(self) -> None:
        self.store.save("att1", "task1", "user_a", "audio/webm", b"x")
        removed = self.store.delete("att1", "task1", "user_a")
        self.assertTrue(removed)
        with self.assertRaises(UploadNotFoundError):
            self.store.load("att1", "task1", "user_a")
        # Idempotent.
        self.assertFalse(self.store.delete("att1", "task1", "user_a"))

    def test_delete_attempt_removes_all_task_files(self) -> None:
        self.store.save("att1", "task1", "user_a", "audio/webm", b"x")
        self.store.save("att1", "task2", "user_a", "audio/webm", b"y")
        # Different attempt under the same user — must survive.
        self.store.save("att2", "task1", "user_a", "audio/webm", b"z")

        removed = self.store.delete_attempt("att1", "user_a")
        self.assertEqual(removed, 2)
        with self.assertRaises(UploadNotFoundError):
            self.store.load("att1", "task1", "user_a")
        with self.assertRaises(UploadNotFoundError):
            self.store.load("att1", "task2", "user_a")
        # att2 still present.
        _, body = self.store.load("att2", "task1", "user_a")
        self.assertEqual(body, b"z")

    def test_delete_attempt_missing_returns_zero(self) -> None:
        self.assertEqual(self.store.delete_attempt("att1", "user_a"), 0)

    # ---- resolved path safety --------------------------------------------

    def test_resolved_path_must_stay_under_base(self) -> None:
        # Build a malicious id that smuggles separators via raw unicode — the
        # store should reject before any filesystem op.
        with self.assertRaises(UnsafeIdentifierError):
            self.store.save(
                attempt_id="att\\..\\escape",
                task_id="task1",
                user_id="user_a",
                content_type="audio/webm",
                stream=b"x",
            )


if __name__ == "__main__":
    unittest.main()
