"""Exam-catalog routes (T-020 / T-020a).

Owns the read-only ``/api/exams/*`` endpoints (catalog list, content,
answer key) plus the practice-feed feed builder. The admin-only mutating
exam endpoints live in :mod:`server_app.routes.admin`.

T-020a moves the actual request-handler bodies out of
:mod:`server_app.core` into this module. The dispatch chain inside
``AppHandler.do_GET`` still owns the path-literal match (so the
modularisation audit test keeps seeing the string literals in
``server_app.core``), but each branch now delegates to a per-route
function defined here. Behaviour is preserved exactly.
"""

from __future__ import annotations

import re
import urllib.parse
from http import HTTPStatus
from typing import TYPE_CHECKING

from server_app.core import (  # noqa: F401
    build_practice_feed,
    list_exam_catalog,
    load_exam_catalog_row,
    load_exam_markdown,
    load_server_answer_key,
    serialize_exam_catalog,
    student_exam_markdown,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from server_app.core import AppHandler


# ---------------------------------------------------------------------------
# Request handler bodies (peeled out of server_app.core in T-020a).
# Each function takes the live ``AppHandler`` instance plus whatever
# extra route-matched arguments (e.g. exam_id, parsed URL) are needed.
# ---------------------------------------------------------------------------


def do_exam_catalog_get(handler: "AppHandler") -> None:
    """``GET /api/exams/catalog`` — list catalog rows visible to the caller."""

    from server_app import core as _core

    session = _core.current_session_record(handler)
    _core.json_response(handler, HTTPStatus.OK, list_exam_catalog(session))


def do_practice_feed_get(
    handler: "AppHandler",
    parsed: urllib.parse.ParseResult,
) -> None:
    """``GET /api/practice-feed`` — build a balanced practice feed."""

    from server_app import core as _core

    try:
        params = urllib.parse.parse_qs(parsed.query)
        count_raw = (params.get("count") or ["12"])[0]
        try:
            count = int(count_raw)
        except ValueError:
            count = 12
        payload = build_practice_feed(
            mode=(params.get("mode") or ["balanced"])[0],
            count=count,
            seed=(params.get("seed") or [None])[0],
        )
        _core.json_response(handler, HTTPStatus.OK, payload)
    except _core.ApiError as error:
        _core.api_error_response(handler, error)


def do_exam_content_get(handler: "AppHandler", exam_id: str) -> None:
    """``GET /api/exams/<exam_id>/content`` — student-safe markdown body."""

    from server_app import core as _core

    try:
        markdown = load_exam_markdown(exam_id)
        _core.text_response(
            handler,
            HTTPStatus.OK,
            student_exam_markdown(markdown),
            "text/markdown; charset=utf-8",
        )
    except _core.ApiError as error:
        _core.api_error_response(handler, error)


def do_exam_answer_key_get(handler: "AppHandler", exam_id: str) -> None:
    """``GET /api/exams/<exam_id>/answer-key`` — answer-key JSON for scoring."""

    from server_app import core as _core

    try:
        answer_key = load_server_answer_key(exam_id)
        _core.json_response(
            handler, HTTPStatus.OK, {"answer_key": answer_key}
        )
    except _core.ApiError as error:
        _core.api_error_response(handler, error)


# Canonical regex patterns for the two dynamic exam routes. Exposed for
# any future call sites that want to match the path without re-typing the
# literal. The dispatcher in :mod:`server_app.core` still uses
# ``re.fullmatch`` against the same pattern strings.
EXAM_CONTENT_RE = re.compile(r"/api/exams/([^/]+)/content")
EXAM_ANSWER_KEY_RE = re.compile(r"/api/exams/([^/]+)/answer-key")


ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/exams/catalog"),
    ("GET", "/api/exams/<exam_id>/content"),
    ("GET", "/api/exams/<exam_id>/answer-key"),
    ("GET", "/api/practice-feed"),
]

__all__ = [
    "EXAM_ANSWER_KEY_RE",
    "EXAM_CONTENT_RE",
    "ROUTES",
    "build_practice_feed",
    "do_exam_answer_key_get",
    "do_exam_catalog_get",
    "do_exam_content_get",
    "do_practice_feed_get",
    "list_exam_catalog",
    "load_exam_catalog_row",
    "load_exam_markdown",
    "load_server_answer_key",
    "serialize_exam_catalog",
    "student_exam_markdown",
]
