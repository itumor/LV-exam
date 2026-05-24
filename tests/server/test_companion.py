"""T-053 — AI tutor companion tests.

Covers the surface added by :mod:`server_app.services.companion`:

1. **Memory persistence** — repeated chats with the same ``user_id``
   update the same row and the conversation counter monotonically
   increases. Two different users never share state.
2. **Summary truncation** — pushing a long memory string through
   :func:`truncate_summary` always returns ≤ 2 KB and the most-recent
   characters are preserved (front-bias trim).
3. **Daily nudge** — the rules-based ``compute_daily_nudge`` returns
   the right ``kind`` and ``severity`` for the five branches
   (welcome / keep_streak / return_gentle / return_strong /
   celebrate_streak).
4. **Full chat path** — a mocked Groq transport flows through
   :func:`generate_chat_reply` and the response surface stays stable.
5. **Quota refund on provider error** — a failed call must not
   permanently consume a slot from the ``ai_quota_ledger``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401  — ensures import side-effects run
from server_app.services import companion as companion_service
from server_app.services import quota as quota_service
from server_app.services.companion import (
    COMPANION_MEMORY_BYTE_BUDGET,
    CompanionInvalidRequest,
    CompanionProviderError,
    NUDGE_GAP_HOURS_GENTLE,
    NUDGE_GAP_HOURS_STRONG,
    NUDGE_KIND_CELEBRATE_STREAK,
    NUDGE_KIND_KEEP_STREAK,
    NUDGE_KIND_RETURN_GENTLE,
    NUDGE_KIND_RETURN_STRONG,
    NUDGE_KIND_WELCOME,
    NUDGE_STREAK_CELEBRATION_DAYS,
    QuotaExceededError,
    compute_daily_nudge,
    generate_chat_reply,
    load_memory,
    nudge_for_account,
    truncate_summary,
    update_memory,
)


def _fake_groq(reply_text: str, usage: dict | None = None):
    """Mocked Groq transport — returns a synthetic chat-completion JSON."""

    def transport(_request, _timeout):  # noqa: ARG001
        return {
            "model": "llama-3.3-70b-versatile",
            "choices": [
                {"message": {"role": "assistant", "content": reply_text}}
            ],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 12},
        }

    return transport


def _failing_groq(exception_factory):
    def transport(_request, _timeout):  # noqa: ARG001
        raise exception_factory()

    return transport


# ---------------------------------------------------------------------------
# 1. Memory truncation (pure function — no DB)
# ---------------------------------------------------------------------------


class CompanionMemoryTruncationTests(unittest.TestCase):
    """``truncate_summary`` must respect the 2 KB byte budget."""

    def test_returns_input_when_below_budget(self) -> None:
        self.assertEqual(truncate_summary(""), "")
        small = "Sveiks!"
        self.assertEqual(truncate_summary(small), small)

    def test_truncates_when_above_budget(self) -> None:
        oversized = "A" * (COMPANION_MEMORY_BYTE_BUDGET + 500)
        trimmed = truncate_summary(oversized)
        self.assertLessEqual(
            len(trimmed.encode("utf-8")),
            COMPANION_MEMORY_BYTE_BUDGET,
            f"truncated payload is still {len(trimmed.encode('utf-8'))} bytes",
        )
        # Front-bias: tail must be preserved verbatim.
        self.assertTrue(trimmed.endswith("A"))
        # And the marker must be present at the front.
        self.assertTrue(trimmed.startswith("…"))

    def test_respects_custom_budget(self) -> None:
        oversized = "x" * 100
        trimmed = truncate_summary(oversized, budget_bytes=20)
        self.assertLessEqual(len(trimmed.encode("utf-8")), 20)

    def test_handles_unicode_diacritics_at_boundary(self) -> None:
        # Each Latvian "ā" is two bytes in UTF-8. Pad with these so the
        # naive byte-slice would land mid-codepoint.
        oversized = "ā" * 2000  # 4000 bytes — well over budget
        trimmed = truncate_summary(oversized)
        # Must still be valid UTF-8 and fit in the budget.
        self.assertLessEqual(len(trimmed.encode("utf-8")), COMPANION_MEMORY_BYTE_BUDGET)
        # And it must be re-decodable cleanly.
        trimmed.encode("utf-8").decode("utf-8")


# ---------------------------------------------------------------------------
# 2. Memory persistence (against a tempfile SQLite DB)
# ---------------------------------------------------------------------------


class CompanionMemoryPersistenceTests(unittest.TestCase):
    """``load_memory`` / ``update_memory`` round-trip through the DB."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        companion_service._reset_companion_ddl_cache()
        server.init_auth_store()
        companion_service.ensure_companion_tables_ready()

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        companion_service._reset_companion_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_load_memory_returns_empty_row_for_new_user(self) -> None:
        row = load_memory("acct_new")
        self.assertEqual(row["user_id"], "acct_new")
        self.assertEqual(row["summary"], "")
        self.assertEqual(row["conversation_count"], 0)
        self.assertEqual(row["last_updated"], "")

    def test_update_memory_persists_and_counter_increments(self) -> None:
        first = update_memory("acct_a", "Labdien!", "Sveiks! Kā tev klājas?")
        self.assertEqual(first["conversation_count"], 1)
        self.assertIn("learner: Labdien!", first["summary"])
        self.assertIn("tutor: Sveiks!", first["summary"])

        second = update_memory("acct_a", "Es mācos latviski.", "Lieliski!")
        self.assertEqual(second["conversation_count"], 2)
        # The previous exchange must still be there.
        self.assertIn("Labdien!", second["summary"])
        self.assertIn("Es mācos latviski.", second["summary"])

        reloaded = load_memory("acct_a")
        self.assertEqual(reloaded["conversation_count"], 2)
        self.assertEqual(reloaded["summary"], second["summary"])

    def test_two_users_do_not_share_memory(self) -> None:
        update_memory("acct_alice", "Es esmu Alise.", "Sveika, Alise!")
        update_memory("acct_bob", "Es esmu Bobs.", "Sveiks, Bob!")

        alice = load_memory("acct_alice")
        bob = load_memory("acct_bob")
        self.assertIn("Alise", alice["summary"])
        self.assertNotIn("Bobs", alice["summary"])
        self.assertIn("Bobs", bob["summary"])
        self.assertNotIn("Alise", bob["summary"])

    def test_memory_stays_within_two_kb_after_many_exchanges(self) -> None:
        # Each exchange is ~80 bytes of fingerprint. 200 of them would
        # blow past the 2 KB budget if we never truncated.
        for index in range(50):
            update_memory(
                "acct_long",
                f"Vingrinājums {index}: kā saka 'sveiks'?",
                f"Mēs sakām 'sveiks' vai 'labdien' (turn {index}).",
            )
        row = load_memory("acct_long")
        self.assertLessEqual(
            len(row["summary"].encode("utf-8")),
            COMPANION_MEMORY_BYTE_BUDGET,
            "memory grew beyond the 2 KB budget after 50 exchanges",
        )
        self.assertEqual(row["conversation_count"], 50)
        # The newest exchange must still be present (front-bias trim).
        self.assertIn("turn 49", row["summary"])

    def test_update_memory_requires_user_id(self) -> None:
        with self.assertRaises(CompanionInvalidRequest):
            update_memory("", "hi", "hello")


# ---------------------------------------------------------------------------
# 3. Daily nudge (pure function — no DB, fixed now)
# ---------------------------------------------------------------------------


class CompanionDailyNudgeTests(unittest.TestCase):
    """``compute_daily_nudge`` branches each return the right shape."""

    NOW = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)

    def _iso(self, dt: datetime) -> str:
        return dt.isoformat().replace("+00:00", "Z")

    def test_welcome_when_no_activity(self) -> None:
        nudge = compute_daily_nudge(
            last_active_at=None, current_streak_days=0, now=self.NOW
        )
        self.assertEqual(nudge.kind, NUDGE_KIND_WELCOME)
        self.assertEqual(nudge.severity, "info")
        self.assertIn("Anete", nudge.message_lv)
        self.assertEqual(nudge.current_streak_days, 0)
        self.assertIsNone(nudge.last_active_at)

    def test_celebrate_streak_at_seven_days(self) -> None:
        last = self.NOW - timedelta(hours=2)
        nudge = compute_daily_nudge(
            last_active_at=self._iso(last),
            current_streak_days=NUDGE_STREAK_CELEBRATION_DAYS,
            now=self.NOW,
        )
        self.assertEqual(nudge.kind, NUDGE_KIND_CELEBRATE_STREAK)
        self.assertEqual(nudge.severity, "celebrate")
        self.assertIn(str(NUDGE_STREAK_CELEBRATION_DAYS), nudge.message_lv)

    def test_celebrate_overrides_recent_activity(self) -> None:
        # Even if they were active 2h ago, a 14-day streak should still
        # render the celebration (not the keep-streak line).
        last = self.NOW - timedelta(hours=2)
        nudge = compute_daily_nudge(
            last_active_at=self._iso(last),
            current_streak_days=14,
            now=self.NOW,
        )
        self.assertEqual(nudge.kind, NUDGE_KIND_CELEBRATE_STREAK)
        self.assertIn("14", nudge.message_lv)

    def test_return_strong_when_gap_above_48h(self) -> None:
        last = self.NOW - timedelta(hours=NUDGE_GAP_HOURS_STRONG + 1)
        nudge = compute_daily_nudge(
            last_active_at=self._iso(last),
            current_streak_days=0,
            now=self.NOW,
        )
        self.assertEqual(nudge.kind, NUDGE_KIND_RETURN_STRONG)
        self.assertEqual(nudge.severity, "warn")

    def test_return_gentle_when_gap_between_24h_and_48h(self) -> None:
        last = self.NOW - timedelta(hours=NUDGE_GAP_HOURS_GENTLE + 1)
        nudge = compute_daily_nudge(
            last_active_at=self._iso(last),
            current_streak_days=0,
            now=self.NOW,
        )
        self.assertEqual(nudge.kind, NUDGE_KIND_RETURN_GENTLE)
        self.assertEqual(nudge.severity, "info")

    def test_keep_streak_when_active_today(self) -> None:
        last = self.NOW - timedelta(hours=4)
        nudge = compute_daily_nudge(
            last_active_at=self._iso(last),
            current_streak_days=3,
            now=self.NOW,
        )
        self.assertEqual(nudge.kind, NUDGE_KIND_KEEP_STREAK)
        self.assertEqual(nudge.severity, "info")
        self.assertEqual(nudge.current_streak_days, 3)

    def test_parses_iso_with_z_suffix(self) -> None:
        # The DB stores last_updated as "...Z" — confirm the parser handles it.
        nudge = compute_daily_nudge(
            last_active_at="2026-05-23T08:00:00Z",
            current_streak_days=2,
            now=self.NOW,
        )
        # Gap is 28 hours — gentle return.
        self.assertEqual(nudge.kind, NUDGE_KIND_RETURN_GENTLE)

    def test_unparseable_iso_falls_back_to_welcome(self) -> None:
        nudge = compute_daily_nudge(
            last_active_at="garbage",
            current_streak_days=0,
            now=self.NOW,
        )
        self.assertEqual(nudge.kind, NUDGE_KIND_WELCOME)


# ---------------------------------------------------------------------------
# 4. End-to-end chat (mocked Groq + tempfile DB)
# ---------------------------------------------------------------------------


class CompanionChatIntegrationTests(unittest.TestCase):
    """Full ``generate_chat_reply`` flow with a mocked LLM transport."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        companion_service._reset_companion_ddl_cache()
        server.init_auth_store()
        companion_service.ensure_companion_tables_ready()

        # Generous quota so the integration tests don't 429.
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
        companion_service._reset_companion_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_first_chat_creates_memory_row(self) -> None:
        result = generate_chat_reply(
            account_id="acct_first",
            plan="free",
            raw_body={"message": "Sveiki, Anete!"},
            transport=_fake_groq("Sveiks! Es priecājos tevi satikt."),
        )
        self.assertEqual(result.reply, "Sveiks! Es priecājos tevi satikt.")
        self.assertEqual(result.memory.conversation_count, 1)
        self.assertGreater(result.memory.summary_bytes, 0)
        self.assertEqual(result.memory.summary_budget_bytes, COMPANION_MEMORY_BYTE_BUDGET)
        self.assertEqual(result.quota["used"], 1)
        # Persisted to the DB.
        reloaded = load_memory("acct_first")
        self.assertEqual(reloaded["conversation_count"], 1)
        self.assertIn("Sveiki, Anete!", reloaded["summary"])

    def test_second_chat_persists_memory(self) -> None:
        generate_chat_reply(
            account_id="acct_persist",
            plan="free",
            raw_body={"message": "Es esmu Mārtiņš."},
            transport=_fake_groq("Patīkami, Mārtiņ!"),
        )
        second = generate_chat_reply(
            account_id="acct_persist",
            plan="free",
            raw_body={"message": "Es dzīvoju Rīgā."},
            transport=_fake_groq("Lieliski!"),
        )
        self.assertEqual(second.memory.conversation_count, 2)
        # Both turns must appear in the persisted summary.
        self.assertIn("Mārtiņš", second.memory.summary)
        self.assertIn("Rīgā", second.memory.summary)

    def test_messages_carry_memory_into_system_prompt(self) -> None:
        # Seed memory.
        update_memory("acct_seed", "Mans vārds ir Anna.", "Sveika, Anna!")
        captured = {}

        def capture(request, _timeout):
            import json as _json
            payload = _json.loads(request.data.decode("utf-8"))
            captured.update(payload)
            return {
                "choices": [{"message": {"content": "Labdien, Anna! Kā šodien iet?"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            }

        generate_chat_reply(
            account_id="acct_seed",
            plan="free",
            raw_body={"message": "Labdien!"},
            transport=capture,
        )
        msgs = captured.get("messages") or []
        # Two system messages — persona + memory — and one user message.
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["system", "system", "user"])
        self.assertIn("Anete", msgs[0]["content"])
        # Memory block must include the previous exchange.
        self.assertIn("Mans vārds ir Anna.", msgs[1]["content"])
        self.assertEqual(msgs[2]["content"], "Labdien!")

    def test_invalid_payload_rejected(self) -> None:
        with self.assertRaises(CompanionInvalidRequest):
            generate_chat_reply(
                account_id="acct_bad",
                plan="free",
                raw_body={"message": ""},
                transport=_fake_groq("…"),
            )
        with self.assertRaises(CompanionInvalidRequest):
            generate_chat_reply(
                account_id="acct_bad",
                plan="free",
                raw_body={},
                transport=_fake_groq("…"),
            )

    def test_quota_exhaustion_raises(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "100",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "2",
            },
            clear=False,
        ):
            for _ in range(2):
                generate_chat_reply(
                    account_id="acct_limit",
                    plan="free",
                    raw_body={"message": "Labdien!"},
                    transport=_fake_groq("Labdien!"),
                )
            with self.assertRaises(QuotaExceededError):
                generate_chat_reply(
                    account_id="acct_limit",
                    plan="free",
                    raw_body={"message": "Vēl viens?"},
                    transport=_fake_groq("…"),
                )

    def test_provider_failure_refunds_quota_slot(self) -> None:
        before = quota_service.AIQuotaLedger().current_usage("acct_refund", "free")
        with self.assertRaises(CompanionProviderError):
            generate_chat_reply(
                account_id="acct_refund",
                plan="free",
                raw_body={"message": "Labdien!"},
                transport=_failing_groq(
                    lambda: CompanionProviderError("simulated outage")
                ),
            )
        after = quota_service.AIQuotaLedger().current_usage("acct_refund", "free")
        self.assertEqual(after, before, "quota slot was not refunded on failure")


# ---------------------------------------------------------------------------
# 5. Nudge backed by stored memory (DB-aware path)
# ---------------------------------------------------------------------------


class CompanionNudgeForAccountTests(unittest.TestCase):
    """``nudge_for_account`` reads the right last-active source."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        companion_service._reset_companion_ddl_cache()
        server.init_auth_store()
        companion_service.ensure_companion_tables_ready()

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        companion_service._reset_companion_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_brand_new_user_gets_welcome_nudge(self) -> None:
        nudge = nudge_for_account("acct_brandnew")
        self.assertEqual(nudge.kind, NUDGE_KIND_WELCOME)

    def test_memory_last_updated_drives_nudge_when_no_xp_streak(self) -> None:
        # Seed a memory row 30 hours in the past.
        from server_app.core import db_connection

        past = datetime.now(timezone.utc) - timedelta(hours=30)
        past_iso = past.isoformat().replace("+00:00", "Z")
        with db_connection() as conn:
            companion_service._ensure_companion_table(conn)
            conn.execute(
                """
                INSERT INTO companion_memory (user_id, summary, last_updated, conversation_count)
                VALUES (?, ?, ?, ?)
                """,
                ("acct_stale", "history", past_iso, 5),
            )
            conn.commit()
        nudge = nudge_for_account("acct_stale")
        self.assertEqual(nudge.kind, NUDGE_KIND_RETURN_GENTLE)


if __name__ == "__main__":
    unittest.main()
