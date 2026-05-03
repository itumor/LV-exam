from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


def test_store_speaking_upload_writes_audio_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "UPLOAD_ROOT", tmp_path / "uploads", raising=False)
    result = server.store_speaking_upload(
        content=b"fake-audio-bytes",
        content_type="audio/webm",
        query={"submission_id": ["submission-123"], "task": ["task1"], "exam_id": ["01"]},
    )

    assert result["submission_id"] == "submission-123"
    assert result["task"] == "task1"
    assert result["upload_url"].startswith("/api/uploads/speaking/")

    meta_path = server.upload_storage_for_id(result["upload_id"])
    assert meta_path.exists()
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata["submission_id"] == "submission-123"
    assert metadata["task"] == "task1"


def test_store_speaking_upload_requires_submission_id(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "UPLOAD_ROOT", tmp_path / "uploads", raising=False)

    with pytest.raises(ValueError, match="submission_id is required"):
        server.store_speaking_upload(
            content=b"fake-audio-bytes",
            content_type="audio/webm",
            query={"task": ["task1"], "exam_id": ["01"]},
        )
