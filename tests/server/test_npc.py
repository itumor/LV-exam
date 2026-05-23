"""T-045 — AI NPC roleplay tests.

Covers the surface added by ``server_app.services.npc``:

1. **NPC load** — every JSON profile in ``content/npcs`` parses, and the
   six expected characters are present.
2. **Response generation** — a mocked Groq transport produces a reply
   that flows back through ``generate_turn`` correctly and uses the
   T-026 quota ledger.
3. **Conversation persistence** — the same ``conversation_id`` is
   returned across calls, history grows, and the SQL row count matches.
4. **Multi-user isolation** — user B cannot read or extend user A's
   conversation even if they supply the same ``conversation_id``.
5. **Schema validation** — invalid payloads raise
   :class:`NPCInvalidRequest` (mirrors the T-026 pydantic contract).
6. **Quota gating** — exhausting the daily ledger raises
   :class:`QuotaExceededError`; the slot is refunded if the provider
   call fails so the user is not punished for a flaky upstream.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401  — ensures package import side-effects run
from server_app.services import npc as npc_service
from server_app.services import quota as quota_service
from server_app.services.npc import (
    NPCInvalidRequest,
    NPCNotFound,
    NPCProviderError,
    QuotaExceededError,
    append_turns,
    build_messages,
    build_system_prompt,
    generate_turn,
    get_or_create_conversation,
    list_npcs,
    load_history,
    load_npc,
    parse_turn_request,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
NPC_CONTENT_DIR = REPO_ROOT / "content" / "npcs"
EXPECTED_NPCS = {
    "cashier-anna",
    "waiter-janis",
    "taxi-maris",
    "doctor-agnese",
    "neighbor-liga",
    "teacher-andris",
}


def _fake_groq(reply_text: str, usage: dict | None = None):
    """Return a transport callable that simulates a successful Groq response."""

    def transport(_request, _timeout):  # noqa: D401, ARG001
        return {
            "model": "llama-3.3-70b-versatile",
            "choices": [
                {"message": {"role": "assistant", "content": reply_text}}
            ],
            "usage": usage or {"prompt_tokens": 120, "completion_tokens": 18},
        }

    return transport


def _failing_groq(exception_factory):
    """Return a transport callable that always raises."""

    def transport(_request, _timeout):  # noqa: ARG001
        raise exception_factory()

    return transport


# ---------------------------------------------------------------------------
# 1. NPC load tests
# ---------------------------------------------------------------------------


class NpcLoadTests(unittest.TestCase):
    """Profile JSON files load and the catalogue is well-formed."""

    def test_content_directory_contains_six_npcs(self) -> None:
        self.assertTrue(NPC_CONTENT_DIR.is_dir(), f"missing dir: {NPC_CONTENT_DIR}")
        files = sorted(p.stem for p in NPC_CONTENT_DIR.glob("*.json"))
        self.assertEqual(set(files), EXPECTED_NPCS)
        self.assertEqual(len(files), 6)

    def test_list_npcs_returns_summary_dicts(self) -> None:
        summaries = list_npcs(NPC_CONTENT_DIR)
        ids = {entry["id"] for entry in summaries}
        self.assertEqual(ids, EXPECTED_NPCS)
        for summary in summaries:
            self.assertIn("name", summary)
            self.assertIn("role", summary)
            self.assertIn("language_level", summary)
            self.assertEqual(summary["language_level"], "A2")

    def test_each_profile_has_required_fields(self) -> None:
        for npc_id in EXPECTED_NPCS:
            profile = load_npc(npc_id, root=NPC_CONTENT_DIR)
            self.assertEqual(profile["id"], npc_id)
            for key in ("name", "role", "persona", "speech_style"):
                self.assertIn(key, profile)
                self.assertTrue(profile[key])
            self.assertIsInstance(profile.get("safety_rules") or [], list)
            self.assertIsInstance(profile.get("common_scenarios") or [], list)

    def test_load_npc_rejects_traversal_ids(self) -> None:
        for bad_id in ("../etc/passwd", "..", "cashier-anna/extra", "a$b"):
            with self.assertRaises(NPCNotFound):
                load_npc(bad_id, root=NPC_CONTENT_DIR)

    def test_load_npc_unknown_raises_not_found(self) -> None:
        with self.assertRaises(NPCNotFound):
            load_npc("does-not-exist", root=NPC_CONTENT_DIR)

    def test_build_system_prompt_contains_persona_signals(self) -> None:
        profile = load_npc("cashier-anna", root=NPC_CONTENT_DIR)
        prompt = build_system_prompt(profile)
        self.assertIn("Anna", prompt)
        self.assertIn("Latvian", prompt)
        self.assertIn("safety", prompt.lower())
        # The hard safety rule from cashier-anna.json must be in the prompt.
        self.assertIn("Es esmu tikai kasiere", prompt)

    def test_build_messages_appends_user_turn_after_history(self) -> None:
        profile = load_npc("waiter-janis", root=NPC_CONTENT_DIR)
        history = [
            {"role": "user", "content": "Labdien!"},
            {"role": "assistant", "content": "Labdien! Ko jūs vēlaties?"},
        ]
        messages = build_messages(profile, history, "Es gribu kafiju.")
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "Es gribu kafiju.")
        # Order preserved.
        self.assertEqual(messages[1]["content"], "Labdien!")
        self.assertEqual(messages[2]["content"], "Labdien! Ko jūs vēlaties?")


# ---------------------------------------------------------------------------
# 2-4. End-to-end turn generation with mocked Groq + DB persistence
# ---------------------------------------------------------------------------


class NpcTurnIntegrationTests(unittest.TestCase):
    """Full turn flow against a tempfile SQLite DB with a mocked LLM."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        # Reset DDL flags so the new tempfile DB gets the tables.
        quota_service._reset_ledger_ddl_cache()
        npc_service._reset_npc_ddl_cache()
        server.init_auth_store()
        npc_service.ensure_npc_tables_ready()

        # Force generous quotas so the integration tests don't 429.
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
        npc_service._reset_npc_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_first_turn_creates_conversation_and_returns_reply(self) -> None:
        result = generate_turn(
            account_id="acct_first",
            plan="free",
            npc_id="cashier-anna",
            raw_body={"message": "Labdien!"},
            npc_root=NPC_CONTENT_DIR,
            transport=_fake_groq("Labdien! Vai jums ir Mans Rimi karte?"),
        )
        self.assertEqual(result.reply, "Labdien! Vai jums ir Mans Rimi karte?")
        self.assertEqual(result.state.npc_id, "cashier-anna")
        self.assertEqual(result.state.turn_index, 2)  # one user + one assistant
        self.assertEqual(result.state.quota_used, 1)
        self.assertGreaterEqual(result.state.quota_limit, 1)
        self.assertTrue(result.state.conversation_id)

    def test_second_turn_appends_to_existing_conversation(self) -> None:
        first = generate_turn(
            account_id="acct_persist",
            plan="free",
            npc_id="waiter-janis",
            raw_body={"message": "Labdien!"},
            npc_root=NPC_CONTENT_DIR,
            transport=_fake_groq("Labdien! Vai jums ir rezervācija?"),
        )
        conv_id = first.state.conversation_id

        second = generate_turn(
            account_id="acct_persist",
            plan="free",
            npc_id="waiter-janis",
            raw_body={"message": "Nē, vai ir brīvs galds?", "conversation_id": conv_id},
            npc_root=NPC_CONTENT_DIR,
            transport=_fake_groq("Jā, lūdzu nāciet šeit."),
        )
        # Same conversation, turn index advances.
        self.assertEqual(second.state.conversation_id, conv_id)
        self.assertEqual(second.state.turn_index, 4)
        # SQL row count matches: 2 user + 2 assistant = 4 turn rows.
        history = load_history("acct_persist", conv_id)
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[3]["content"], "Jā, lūdzu nāciet šeit.")

    def test_groq_is_called_with_persona_system_prompt(self) -> None:
        captured = {}

        def capturing_transport(request, _timeout):
            payload = json.loads(request.data.decode("utf-8"))
            captured.update(payload)
            return {
                "choices": [{"message": {"content": "Sveiks, mans draugs!"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            }

        generate_turn(
            account_id="acct_prompt",
            plan="free",
            npc_id="neighbor-liga",
            raw_body={"message": "Labrīt!"},
            npc_root=NPC_CONTENT_DIR,
            transport=capturing_transport,
        )
        messages = captured.get("messages") or []
        self.assertTrue(messages)
        self.assertEqual(messages[0]["role"], "system")
        # Persona content is in the system message.
        self.assertIn("Līga", messages[0]["content"])
        self.assertIn("kaimiņiene", messages[0]["content"])
        # User message appears verbatim at the end.
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "Labrīt!")
        # Default Groq model is the llama-3.3-70b family.
        self.assertIn("llama-3.3-70b", captured.get("model", ""))

    def test_multi_user_isolation_other_account_cannot_read_history(self) -> None:
        first = generate_turn(
            account_id="acct_alice",
            plan="free",
            npc_id="taxi-maris",
            raw_body={"message": "Uz lidostu, lūdzu."},
            npc_root=NPC_CONTENT_DIR,
            transport=_fake_groq("Labi, ejam."),
        )
        conv_id = first.state.conversation_id

        # Alice can read her own history.
        alice_history = load_history("acct_alice", conv_id)
        self.assertEqual(len(alice_history), 2)

        # Bob supplying Alice's conversation_id MUST NOT see it.
        bob_history = load_history("acct_bob", conv_id)
        self.assertEqual(bob_history, [])

        # When Bob posts with Alice's conversation_id, the service should
        # treat it as "not yours, start a fresh conversation" — never leak
        # Alice's turns.
        bob_turn = generate_turn(
            account_id="acct_bob",
            plan="free",
            npc_id="taxi-maris",
            raw_body={"message": "Sveiks!", "conversation_id": conv_id},
            npc_root=NPC_CONTENT_DIR,
            transport=_fake_groq("Sveiks! Kurp braucam?"),
        )
        self.assertNotEqual(bob_turn.state.conversation_id, conv_id)
        # Alice's row count is unchanged (no leakage / mutation).
        self.assertEqual(len(load_history("acct_alice", conv_id)), 2)

    def test_quota_is_reserved_and_reported_in_state(self) -> None:
        first = generate_turn(
            account_id="acct_q",
            plan="free",
            npc_id="cashier-anna",
            raw_body={"message": "Labdien!"},
            npc_root=NPC_CONTENT_DIR,
            transport=_fake_groq("Labdien!"),
        )
        self.assertEqual(first.state.quota_used, 1)
        second = generate_turn(
            account_id="acct_q",
            plan="free",
            npc_id="cashier-anna",
            raw_body={"message": "Cik maksā?", "conversation_id": first.state.conversation_id},
            npc_root=NPC_CONTENT_DIR,
            transport=_fake_groq("Pieci eiro."),
        )
        self.assertEqual(second.state.quota_used, 2)

    def test_quota_exhaustion_raises_429_style_error(self) -> None:
        # Tighten the cap so we hit it after 2 calls.
        with patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "100",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "2",
            },
            clear=False,
        ):
            for _ in range(2):
                generate_turn(
                    account_id="acct_limit",
                    plan="free",
                    npc_id="cashier-anna",
                    raw_body={"message": "Labdien!"},
                    npc_root=NPC_CONTENT_DIR,
                    transport=_fake_groq("Labdien!"),
                )
            with self.assertRaises(QuotaExceededError) as ctx:
                generate_turn(
                    account_id="acct_limit",
                    plan="free",
                    npc_id="cashier-anna",
                    raw_body={"message": "Vēl viens jautājums?"},
                    npc_root=NPC_CONTENT_DIR,
                    transport=_fake_groq("…"),
                )
            self.assertEqual(ctx.exception.status_code, 429)

    def test_provider_failure_refunds_quota_slot(self) -> None:
        # Run a failing turn and confirm the ledger does not stay at +1.
        before = quota_service.AIQuotaLedger().current_usage("acct_refund", "free")
        with self.assertRaises(NPCProviderError):
            generate_turn(
                account_id="acct_refund",
                plan="free",
                npc_id="cashier-anna",
                raw_body={"message": "Labdien!"},
                npc_root=NPC_CONTENT_DIR,
                transport=_failing_groq(lambda: NPCProviderError("simulated outage")),
            )
        after = quota_service.AIQuotaLedger().current_usage("acct_refund", "free")
        self.assertEqual(after, before)

    def test_invalid_request_payload_rejected(self) -> None:
        # Empty message — fails pydantic min_length.
        with self.assertRaises(NPCInvalidRequest):
            generate_turn(
                account_id="acct_bad",
                plan="free",
                npc_id="cashier-anna",
                raw_body={"message": ""},
                npc_root=NPC_CONTENT_DIR,
                transport=_fake_groq("…"),
            )
        # Missing message entirely.
        with self.assertRaises(NPCInvalidRequest):
            generate_turn(
                account_id="acct_bad",
                plan="free",
                npc_id="cashier-anna",
                raw_body={},
                npc_root=NPC_CONTENT_DIR,
                transport=_fake_groq("…"),
            )

    def test_unknown_npc_id_raises_not_found(self) -> None:
        with self.assertRaises(NPCNotFound):
            generate_turn(
                account_id="acct_404",
                plan="free",
                npc_id="ghost",
                raw_body={"message": "Labdien!"},
                npc_root=NPC_CONTENT_DIR,
                transport=_fake_groq("…"),
            )

    def test_parse_turn_request_accepts_minimal_payload(self) -> None:
        parsed = parse_turn_request({"message": "Hello"})
        self.assertEqual(parsed.message, "Hello")
        self.assertIsNone(parsed.conversation_id)

    def test_parse_turn_request_trims_conversation_id(self) -> None:
        parsed = parse_turn_request({"message": "Hi", "conversation_id": "  "})
        self.assertIsNone(parsed.conversation_id)
        parsed2 = parse_turn_request({"message": "Hi", "conversation_id": "abc"})
        self.assertEqual(parsed2.conversation_id, "abc")


# ---------------------------------------------------------------------------
# Lower-level persistence helpers (additional defence-in-depth)
# ---------------------------------------------------------------------------


class NpcPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        npc_service._reset_npc_ddl_cache()
        server.init_auth_store()
        npc_service.ensure_npc_tables_ready()

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        npc_service._reset_npc_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_get_or_create_returns_existing_when_id_provided(self) -> None:
        first = get_or_create_conversation("acct_x", "cashier-anna", None)
        second = get_or_create_conversation("acct_x", "cashier-anna", first["id"])
        self.assertEqual(first["id"], second["id"])

    def test_get_or_create_ignores_cross_account_id(self) -> None:
        owned = get_or_create_conversation("acct_a", "cashier-anna", None)
        leaked = get_or_create_conversation("acct_b", "cashier-anna", owned["id"])
        self.assertNotEqual(leaked["id"], owned["id"])

    def test_append_turns_increments_turn_count(self) -> None:
        conv = get_or_create_conversation("acct_t", "cashier-anna", None)
        self.assertEqual(conv["turn_count"], 0)
        conv = append_turns("acct_t", conv, "Labdien!", "Labdien jums!")
        self.assertEqual(conv["turn_count"], 2)
        history = load_history("acct_t", conv["id"])
        self.assertEqual(history[0]["content"], "Labdien!")
        self.assertEqual(history[1]["content"], "Labdien jums!")


if __name__ == "__main__":
    unittest.main()
