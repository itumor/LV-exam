"""AI curriculum routes (T-054).

Two HTTP routes:

* ``POST /api/curriculum/generate`` — generate (or fetch from cache) a
                                       personalised micro-lesson for the
                                       caller. Body shape is
                                       :class:`GenerateLessonRequest`.
* ``GET  /api/curriculum/lessons``  — list the caller's cached lessons
                                       (newest first, expired rows
                                       filtered out by default).

The actual dispatch wiring lives in :mod:`server_app.core` (T-054 hook
block) — same pattern as T-031 / T-034 / T-053. This module is the
per-domain re-export so the modularisation audit can attribute the
routes to a single owner.
"""

from __future__ import annotations

from server_app.services.curriculum import (  # noqa: F401
    CURRICULUM_SYSTEM_PROMPT,
    CurriculumError,
    CurriculumInvalidRequest,
    CurriculumProviderError,
    GenerateLessonRequest,
    LESSON_CACHE_TTL_SECONDS,
    LESSON_LIST_LIMIT,
    LessonContent,
    LessonDrill,
    LessonRecord,
    LessonVocabItem,
    QuotaExceededError,
    ensure_curriculum_tables_ready,
    gather_srs_seed,
    generate_lesson,
    list_lessons,
    list_lessons_for_route,
    parse_generate_request,
    parse_lesson_content,
    resolve_weak_skill,
)


ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/curriculum/generate"),
    ("GET", "/api/curriculum/lessons"),
]


__all__ = [
    "CURRICULUM_SYSTEM_PROMPT",
    "CurriculumError",
    "CurriculumInvalidRequest",
    "CurriculumProviderError",
    "GenerateLessonRequest",
    "LESSON_CACHE_TTL_SECONDS",
    "LESSON_LIST_LIMIT",
    "LessonContent",
    "LessonDrill",
    "LessonRecord",
    "LessonVocabItem",
    "QuotaExceededError",
    "ROUTES",
    "ensure_curriculum_tables_ready",
    "gather_srs_seed",
    "generate_lesson",
    "list_lessons",
    "list_lessons_for_route",
    "parse_generate_request",
    "parse_lesson_content",
    "resolve_weak_skill",
]
