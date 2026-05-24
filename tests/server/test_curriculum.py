"""T-054 — AI curriculum generator tests.

Covers the deliverables called out in the T-054 brief:

1. **Mocked Groq lesson generation** — a stubbed transport flows through
   :func:`curriculum.generate_lesson` and returns a validated lesson body.
2. **Cache determinism per weak-skill** — repeated calls with the same
   ``(account_id, weak_skill, srs_seed)`` triple hit the cache (no second
   Groq round-trip) and return the same ``lesson_id``.
3. **Cache TTL** — once the lesson's ``expires_at`` is past, the next
   call performs a fresh Groq round-trip and updates the row.
4. **SRS-seed sensitivity** — adding a card to the SRS deck shifts the
   cache key so the new lesson is generated rather than served stale.
5. **Readiness-driven weak-skill auto-detection** — when the caller omits
   ``weak_skill``, the service derives it from T-030 readiness.
6. **Quota debit on miss / refund on provider error** — same pattern as
   the companion / NPC services.
7. **Schema rejection** — a malformed Groq reply raises
   :class:`CurriculumProviderError`.
8. **Routes wiring** — both ``/api/curriculum/*`` paths are present in
   ``server_app.routes.curriculum.ROUTES``, and the install marker
   ``_t054_installed`` is set on ``AppHandler``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import server  # noqa: E402 — registers route hooks at import time.
from server_app.services import curriculum as curriculum_service  # noqa: E402
from server_app.services import quota as quota_service  # noqa: E402
from server_app.services import srs as srs_service  # noqa: E402
from server_app.services import schema_a2  # noqa: E402
from server_app.routes import curriculum as curriculum_routes  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_LESSON_BODY = {
    "title": "Sarunas slimnīcā",
    "objective": "Saprast pacienta sūdzības par sāpēm.",
    "vocab": [
        {"lv": "sāpes", "en": "pain"},
        {"lv": "ārsts", "en": "doctor"},
    ],
    "drills": [
        {
            "prompt_lv": "Pārtulko: 'I have a headache.'",
            "prompt_en": "Translate: 'I have a headache.'",
            "answer_lv": "Man sāp galva.",
            "rationale_en": "Dative + sāpēt construction.",
        },
        {
            "prompt_lv": "Aizpildi: Es ___ pie ārsta.",
            "prompt_en": "Fill in: I am going to the doctor.",
            "answer_lv": "eju",
            "rationale_en": "Present 1sg of 'iet'.",
        },
    ],
    "reflection_prompt_en": "Which word was hardest to recall?",
}


def _fake_groq(reply_payload, usage: dict | None = None):
    """Synthetic Groq transport — returns ``reply_payload`` as the content.

    ``reply_payload`` may be a ``dict`` (auto-JSON-encoded) or a raw
    ``str`` (used for malformed-reply tests).
    """

    if isinstance(reply_payload, dict):
        content = json.dumps(reply_payload, ensure_ascii=False)
    else:
        content = str(reply_payload)

    def transport(_request, _timeout):  # noqa: ARG001
        return {
            "model": "llama-3.3-70b-versatile",
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": usage or {"prompt_tokens": 250, "completion_tokens": 80},
        }

    return transport


def _counting_groq(reply_payload, counter: dict[str, int]):
    """Same as ``_fake_groq`` but bumps ``counter['calls']`` on each call.

    Used by the cache-determinism tests to assert how many Groq round
    trips actually happened.
    """

    content = json.dumps(reply_payload, ensure_ascii=False)

    def transport(_request, _timeout):  # noqa: ARG001
        counter["calls"] = counter.get("calls", 0) + 1
        return {
            "model": "llama-3.3-70b-versatile",
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 250, "completion_tokens": 80},
        }

    return transport


def _failing_groq(exception_factory):
    def transport(_request, _timeout):  # noqa: ARG001
        raise exception_factory()

    return transport


def _seed_account(account_id: str, email: str) -> None:
    with server.db_connection() as conn:
        conn.execute(
            """
            INSERT INTO accounts (id, email, password_salt, password_hash,
                                  status, created_at, deleted_at)
            VALUES (?, ?, 'salt', 'hash', 'active',
                    '2026-05-23T00:00:00Z', NULL)
            """,
            (account_id, email),
        )


def _seed_attempt_score(
    *,
    account_id: str,
    attempt_id: str,
    skill: str,
    score: int,
    created_at: str = "2026-05-23T00:00:00Z",
) -> None:
    with server.db_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO attempts
            (id, account_id, exam_id, exam_title, status, submitted_at,
             score_total, score_payload, submission_payload,
             created_at, updated_at)
            VALUES (?, ?, 'a2-builtin', 'A2 Mock', 'submitted', ?,
                    NULL, '{}', '{}', ?, ?)
            """,
            (attempt_id, account_id, created_at, created_at, created_at),
        )
        conn.execute(
            """
            INSERT INTO exam_attempt_category_score
            (id, attempt_id, account_id, category, score_0_to_15,
             passed_boolean, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"eacs_{attempt_id}_{skill}",
                attempt_id,
                account_id,
                skill,
                int(score),
                1 if score >= schema_a2.A2_MIN_PER_SKILL else 0,
                created_at,
            ),
        )


# ---------------------------------------------------------------------------
# Base fixture — fresh tmp DB per test.
# ---------------------------------------------------------------------------


class _CurriculumTestBase(unittest.TestCase):
    """Shared scaffolding: tmp SQLite DB + reset DDL caches + seeded account."""

    ACCOUNT_ID = "acct_t054"
    EMAIL = "learner@example.test"

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        srs_service._reset_ddl_cache_for_tests()
        curriculum_service._reset_curriculum_ddl_cache()
        server.init_auth_store()
        with server.db_connection() as conn:
            srs_service.ensure_srs_schema(conn)
        curriculum_service.ensure_curriculum_tables_ready()
        _seed_account(self.ACCOUNT_ID, self.EMAIL)

        # Generous quota for tests.
        self.env_patch = patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "50",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "20",
                "AI_SCORING_DAILY_REQUEST_LIMIT_PRO": "50",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        curriculum_service._reset_curriculum_ddl_cache()
        srs_service._reset_ddl_cache_for_tests()
        quota_service._reset_ledger_ddl_cache()


# ---------------------------------------------------------------------------
# 1. Lesson generation through a mocked Groq transport
# ---------------------------------------------------------------------------


class CurriculumGenerationTests(_CurriculumTestBase):
    """End-to-end ``generate_lesson`` with a stubbed transport."""

    def test_first_call_generates_and_persists(self) -> None:
        result = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="listening",
            plan="free",
            transport=_fake_groq(_DEFAULT_LESSON_BODY),
        )
        self.assertFalse(result["cached"])
        self.assertEqual(result["weak_skill"], "listening")
        self.assertEqual(
            result["content"]["title"], _DEFAULT_LESSON_BODY["title"]
        )
        self.assertEqual(len(result["content"]["drills"]), 2)
        self.assertEqual(result["quota"]["used"], 1)
        # Lesson should be persisted now.
        listed = curriculum_service.list_lessons(self.ACCOUNT_ID)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].weak_skill, "listening")

    def test_response_includes_expires_at_in_future(self) -> None:
        anchor = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
        result = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="reading",
            plan="free",
            transport=_fake_groq(_DEFAULT_LESSON_BODY),
            now=anchor,
        )
        expires = curriculum_service._parse_iso(result["expires_at"])
        self.assertIsNotNone(expires)
        # 24 h TTL → expires anchor + 24h.
        self.assertEqual(expires, anchor + timedelta(hours=24))


# ---------------------------------------------------------------------------
# 2. Cache determinism per weak skill (same input → no second Groq call)
# ---------------------------------------------------------------------------


class CurriculumCacheDeterminismTests(_CurriculumTestBase):
    """Two calls with the same inputs MUST hit the cache (no extra Groq call)."""

    def test_second_call_with_same_skill_hits_cache(self) -> None:
        counter = {"calls": 0}
        transport = _counting_groq(_DEFAULT_LESSON_BODY, counter)

        first = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="writing",
            plan="free",
            transport=transport,
        )
        second = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="writing",
            plan="free",
            transport=transport,
        )

        self.assertEqual(counter["calls"], 1, "second call must not hit Groq")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["lesson_id"], second["lesson_id"])
        self.assertEqual(first["cache_key"], second["cache_key"])
        # No quota debit on cache hit (snapshot is empty for cached lessons).
        self.assertEqual(second["quota"], {})

    def test_different_skills_use_different_cache_keys(self) -> None:
        counter = {"calls": 0}
        transport = _counting_groq(_DEFAULT_LESSON_BODY, counter)

        listening = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="listening",
            plan="free",
            transport=transport,
        )
        reading = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="reading",
            plan="free",
            transport=transport,
        )

        self.assertEqual(counter["calls"], 2, "different skills must each call Groq")
        self.assertNotEqual(listening["cache_key"], reading["cache_key"])
        self.assertNotEqual(listening["lesson_id"], reading["lesson_id"])

    def test_force_refresh_bypasses_cache(self) -> None:
        counter = {"calls": 0}
        transport = _counting_groq(_DEFAULT_LESSON_BODY, counter)

        curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="speaking",
            plan="free",
            transport=transport,
        )
        forced = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="speaking",
            plan="free",
            transport=transport,
            force_refresh=True,
        )

        self.assertEqual(counter["calls"], 2, "force_refresh must hit Groq")
        self.assertFalse(forced["cached"])


# ---------------------------------------------------------------------------
# 3. Cache TTL — expired entries trigger a fresh generation
# ---------------------------------------------------------------------------


class CurriculumCacheTtlTests(_CurriculumTestBase):
    """A lesson whose ``expires_at`` is in the past is regenerated."""

    def test_expired_lesson_is_regenerated(self) -> None:
        counter = {"calls": 0}
        transport = _counting_groq(_DEFAULT_LESSON_BODY, counter)

        anchor = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)
        first = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="reading",
            plan="free",
            transport=transport,
            now=anchor,
        )
        self.assertEqual(counter["calls"], 1)
        self.assertFalse(first["cached"])

        # 25 hours later → past the 24 h TTL.
        later = anchor + timedelta(hours=25)
        second = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="reading",
            plan="free",
            transport=transport,
            now=later,
        )
        self.assertEqual(counter["calls"], 2, "TTL miss must regenerate")
        self.assertFalse(second["cached"])
        # Same cache_key (the inputs didn't change), but the row was overwritten.
        self.assertEqual(first["cache_key"], second["cache_key"])
        # Only one row should ever exist for a key.
        listed = curriculum_service.list_lessons(
            self.ACCOUNT_ID, include_expired=True, now=later
        )
        cache_keys = [r.cache_key for r in listed]
        self.assertEqual(cache_keys.count(first["cache_key"]), 1)

    def test_lesson_within_ttl_is_served_from_cache(self) -> None:
        counter = {"calls": 0}
        transport = _counting_groq(_DEFAULT_LESSON_BODY, counter)

        anchor = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)
        curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="writing",
            plan="free",
            transport=transport,
            now=anchor,
        )

        # Still within the 24h TTL.
        inside_ttl = anchor + timedelta(hours=23, minutes=59)
        result = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="writing",
            plan="free",
            transport=transport,
            now=inside_ttl,
        )
        self.assertEqual(counter["calls"], 1, "must not call Groq within TTL")
        self.assertTrue(result["cached"])


# ---------------------------------------------------------------------------
# 4. SRS-seed sensitivity
# ---------------------------------------------------------------------------


class CurriculumSrsSeedTests(_CurriculumTestBase):
    """Adding a card to the SRS deck shifts the cache key."""

    def test_adding_a_card_invalidates_the_cache_key(self) -> None:
        counter = {"calls": 0}
        transport = _counting_groq(_DEFAULT_LESSON_BODY, counter)

        first = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="listening",
            plan="free",
            transport=transport,
        )

        # Add a card to the SRS deck — this should shift the cache key.
        with server.db_connection() as conn:
            srs_service.add_card(
                conn, self.ACCOUNT_ID, "māja", "māja", "house"
            )

        second = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="listening",
            plan="free",
            transport=transport,
        )
        self.assertEqual(counter["calls"], 2, "new SRS seed must regenerate")
        self.assertNotEqual(first["cache_key"], second["cache_key"])

    def test_compute_cache_key_is_order_invariant(self) -> None:
        seed_a = [
            {"lv": "māja", "en": "house"},
            {"lv": "ārsts", "en": "doctor"},
        ]
        seed_b = list(reversed(seed_a))
        key_a = curriculum_service.compute_cache_key("acct_x", "listening", seed_a)
        key_b = curriculum_service.compute_cache_key("acct_x", "listening", seed_b)
        self.assertEqual(
            key_a, key_b, "seed order must not affect the cache key hash"
        )


# ---------------------------------------------------------------------------
# 5. Readiness-driven weak-skill auto-detection
# ---------------------------------------------------------------------------


class CurriculumReadinessTests(_CurriculumTestBase):
    """When ``weak_skill`` is None, the service picks the worst-scoring skill."""

    def test_no_history_falls_back_to_listening(self) -> None:
        skill = curriculum_service.resolve_weak_skill(
            self.ACCOUNT_ID, explicit_skill=None
        )
        # With no exam_attempt_category_score rows, every skill is "no
        # history" so the canonical first-skill (listening) wins.
        self.assertEqual(skill, "listening")

    def test_lowest_score_skill_is_selected(self) -> None:
        # Seed: speaking 4/15 (worst), listening 12/15, reading 11, writing 10.
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_a",
            skill="listening",
            score=12,
        )
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_a",
            skill="reading",
            score=11,
        )
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_a",
            skill="writing",
            score=10,
        )
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_a",
            skill="speaking",
            score=4,
        )
        skill = curriculum_service.resolve_weak_skill(
            self.ACCOUNT_ID, explicit_skill=None
        )
        self.assertEqual(skill, "speaking")

    def test_explicit_skill_overrides_readiness(self) -> None:
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_b",
            skill="speaking",
            score=4,
        )
        skill = curriculum_service.resolve_weak_skill(
            self.ACCOUNT_ID, explicit_skill="writing"
        )
        self.assertEqual(skill, "writing")

    def test_generate_lesson_without_weak_skill_uses_readiness(self) -> None:
        # All four skills seeded so "no history" doesn't outrank a real
        # low score in the auto-detection tie-breaker.
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_c",
            skill="listening",
            score=12,
        )
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_c",
            skill="reading",
            score=6,  # worst — should be picked
        )
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_c",
            skill="writing",
            score=10,
        )
        _seed_attempt_score(
            account_id=self.ACCOUNT_ID,
            attempt_id="att_c",
            skill="speaking",
            score=11,
        )
        result = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill=None,  # auto-detect
            plan="free",
            transport=_fake_groq(_DEFAULT_LESSON_BODY),
        )
        self.assertEqual(result["weak_skill"], "reading")


# ---------------------------------------------------------------------------
# 6. Quota — debited on miss, refunded on provider error
# ---------------------------------------------------------------------------


class CurriculumQuotaTests(_CurriculumTestBase):
    """Quota plumbing mirrors the companion / NPC pattern."""

    def test_cache_hit_does_not_debit_quota(self) -> None:
        transport = _fake_groq(_DEFAULT_LESSON_BODY)
        # First call (miss) debits one slot.
        curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="reading",
            plan="free",
            transport=transport,
        )
        ledger = quota_service.AIQuotaLedger()
        used_after_first = ledger.current_usage(self.ACCOUNT_ID, "free")
        self.assertEqual(used_after_first, 1)

        # Second call (hit) must NOT debit.
        curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="reading",
            plan="free",
            transport=transport,
        )
        used_after_second = ledger.current_usage(self.ACCOUNT_ID, "free")
        self.assertEqual(used_after_second, 1, "cache hit must not debit quota")

    def test_provider_error_refunds_quota(self) -> None:
        ledger = quota_service.AIQuotaLedger()
        before = ledger.current_usage(self.ACCOUNT_ID, "free")
        with self.assertRaises(curriculum_service.CurriculumProviderError):
            curriculum_service.generate_lesson(
                account_id=self.ACCOUNT_ID,
                weak_skill="reading",
                plan="free",
                transport=_failing_groq(
                    lambda: curriculum_service.CurriculumProviderError(
                        "simulated outage"
                    )
                ),
            )
        after = ledger.current_usage(self.ACCOUNT_ID, "free")
        self.assertEqual(after, before, "quota slot must be refunded on failure")


# ---------------------------------------------------------------------------
# 7. Schema rejection — malformed Groq replies
# ---------------------------------------------------------------------------


class CurriculumSchemaTests(_CurriculumTestBase):
    """The lesson schema is enforced at the service boundary."""

    def test_empty_reply_is_rejected(self) -> None:
        with self.assertRaises(curriculum_service.CurriculumProviderError):
            curriculum_service.generate_lesson(
                account_id=self.ACCOUNT_ID,
                weak_skill="reading",
                plan="free",
                transport=_fake_groq(""),
            )

    def test_non_json_reply_is_rejected(self) -> None:
        with self.assertRaises(curriculum_service.CurriculumProviderError):
            curriculum_service.generate_lesson(
                account_id=self.ACCOUNT_ID,
                weak_skill="reading",
                plan="free",
                transport=_fake_groq("Sorry, I cannot help with that."),
            )

    def test_missing_required_field_is_rejected(self) -> None:
        bad = dict(_DEFAULT_LESSON_BODY)
        bad.pop("title")
        with self.assertRaises(curriculum_service.CurriculumProviderError):
            curriculum_service.generate_lesson(
                account_id=self.ACCOUNT_ID,
                weak_skill="reading",
                plan="free",
                transport=_fake_groq(bad),
            )

    def test_no_drills_is_rejected(self) -> None:
        bad = dict(_DEFAULT_LESSON_BODY)
        bad["drills"] = []
        with self.assertRaises(curriculum_service.CurriculumProviderError):
            curriculum_service.generate_lesson(
                account_id=self.ACCOUNT_ID,
                weak_skill="reading",
                plan="free",
                transport=_fake_groq(bad),
            )

    def test_unknown_skill_in_payload_is_rejected(self) -> None:
        with self.assertRaises(curriculum_service.CurriculumInvalidRequest):
            curriculum_service.parse_generate_request({"weak_skill": "alchemy"})

    def test_markdown_fenced_json_is_extracted(self) -> None:
        """Groq sometimes wraps JSON in ```json fences — we must still parse."""

        wrapped = "```json\n" + json.dumps(_DEFAULT_LESSON_BODY) + "\n```"
        result = curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="reading",
            plan="free",
            transport=_fake_groq(wrapped),
        )
        self.assertFalse(result["cached"])
        self.assertEqual(
            result["content"]["title"], _DEFAULT_LESSON_BODY["title"]
        )


# ---------------------------------------------------------------------------
# 8. List lessons (route payload)
# ---------------------------------------------------------------------------


class CurriculumListLessonsTests(_CurriculumTestBase):
    """``list_lessons_for_route`` returns the route-shaped payload."""

    def test_empty_when_no_lessons_generated(self) -> None:
        payload = curriculum_service.list_lessons_for_route(self.ACCOUNT_ID)
        self.assertEqual(payload["lessons"], [])
        self.assertEqual(payload["count"], 0)

    def test_returns_most_recent_first(self) -> None:
        transport = _fake_groq(_DEFAULT_LESSON_BODY)
        curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="listening",
            plan="free",
            transport=transport,
        )
        curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="reading",
            plan="free",
            transport=transport,
        )
        payload = curriculum_service.list_lessons_for_route(self.ACCOUNT_ID)
        self.assertEqual(payload["count"], 2)
        skills = [row["weak_skill"] for row in payload["lessons"]]
        # Newest first → reading was generated last.
        self.assertEqual(skills[0], "reading")
        self.assertEqual(skills[1], "listening")

    def test_expired_lessons_are_filtered_out(self) -> None:
        anchor = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)
        curriculum_service.generate_lesson(
            account_id=self.ACCOUNT_ID,
            weak_skill="listening",
            plan="free",
            transport=_fake_groq(_DEFAULT_LESSON_BODY),
            now=anchor,
        )
        # Look two days later — past the 24h TTL.
        later = anchor + timedelta(days=2)
        payload = curriculum_service.list_lessons_for_route(
            self.ACCOUNT_ID, now=later
        )
        self.assertEqual(payload["count"], 0, "expired lessons must not surface")


# ---------------------------------------------------------------------------
# 9. Routes wiring — hooks installed on AppHandler
# ---------------------------------------------------------------------------


class CurriculumRoutesWiringTests(unittest.TestCase):
    """Structural test — ROUTES list + install marker on the handler class."""

    def test_routes_exposed_in_module(self) -> None:
        paths = {(method, path) for method, path in curriculum_routes.ROUTES}
        self.assertIn(("POST", "/api/curriculum/generate"), paths)
        self.assertIn(("GET", "/api/curriculum/lessons"), paths)

    def test_install_marker_present(self) -> None:
        # The T-054 hook installer sets this attribute when the route
        # patches are wired against AppHandler at import time.
        self.assertTrue(
            getattr(server.AppHandler, "_t054_installed", False),
            "T-054 route hook did not install on AppHandler",
        )


if __name__ == "__main__":
    unittest.main()
