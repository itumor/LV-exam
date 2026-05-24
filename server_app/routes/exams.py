"""Exam-catalog routes (T-020).

Owns the read-only ``/api/exams/*`` endpoints (catalog list, content,
answer key) plus the practice-feed feed builder. The admin-only mutating
exam endpoints live in :mod:`server_app.routes.admin`.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    build_practice_feed,
    list_exam_catalog,
    load_exam_catalog_row,
    load_exam_markdown,
    load_server_answer_key,
    serialize_exam_catalog,
    student_exam_markdown,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/exams/catalog"),
    ("GET", "/api/exams/<exam_id>/content"),
    ("GET", "/api/exams/<exam_id>/answer-key"),
    ("GET", "/api/practice-feed"),
]

__all__ = [
    "ROUTES",
    "build_practice_feed",
    "list_exam_catalog",
    "load_exam_catalog_row",
    "load_exam_markdown",
    "load_server_answer_key",
    "serialize_exam_catalog",
    "student_exam_markdown",
]
