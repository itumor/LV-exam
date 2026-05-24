"""T-055 — Procedural story generator tests.

Covers :mod:`server_app.services.procedural_story`:

1. **Chapter generation (mocked Groq)** — a single LLM call goes through
   :func:`generate_chapter`, the response surface (``chapter``,
   ``state``, ``quota``, ``usage``) is stable, and the new chapter is
   persisted to the ``procedural_stories`` row.
2. **Branching state** — choosing distinct ``choice_id`` values produces
   distinct *paths* in the persisted history. Two learners on the same
   seed but different choices never share state.
3. **Coherence** — chapter N's prompt (the LLM messages array) must
   mention the most recent previous choice the learner made. This is
   the strongest signal that the narrative honours its branching
   contract.
4. **Resilience** — corrupt history rows degrade to an empty state
   instead of erroring; provider failures refund the quota slot;
   invalid choice ids raise the right typed error.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401  — triggers side-effect hook installation
from server_app.services import procedural_story as story_service
from server_app.services import quota as quota_service
from server_app.services.procedural_story import (
    MAX_CHAPTERS_PER_STORY,
    MAX_CHOICES,
    MIN_CHOICES,
    PROCEDURAL_SYSTEM_PROMPT,
    ChoiceOption,
    ProceduralStoryFinished,
    ProceduralStoryInvalidRequest,
    ProceduralStoryProviderError,
    QuotaExceededError,
    StoryChapter,
    build_messages,
    generate_chapter,
    load_state,
    reset_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_groq_response(
    narrative: str,
    choices: list[dict[str, str]] | None = None,
    *,
    usage: dict | None = None,
) -> dict:
    """Synthetic Groq chat-completion payload for a single chapter."""

    if choices is None:
        choices = [
            {"id": "A", "label": "Tu ej iekšā."},
            {"id": "B", "label": "Tu paliec ārā."},
        ]
    content = json.dumps({"narrative": narrative, "choices": choices}, ensure_ascii=False)
    return {
        "model": "llama-3.3-70b-versatile",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": usage or {"prompt_tokens": 120, "completion_tokens": 80},
    }


def _scripted_groq(*responses: dict):
    """Return a transport that yields the given responses in order.

    The very last response is repeated for any further calls (so a test
    that exercises a long chain doesn't need to enumerate every turn).
    """

    state = {"index": 0}

    def transport(request, _timeout):  # noqa: ARG001
        idx = min(state["index"], len(responses) - 1)
        state["index"] += 1
        return responses[idx]

    return transport, state


def _capturing_groq(response: dict):
    """Return a transport that records the request payload."""

    captured: dict = {}

    def transport(request, _timeout):  # noqa: ARG001
        try:
            captured.update(json.loads(request.data.decode("utf-8")))
        except Exception:  # noqa: BLE001 — best-effort capture
            pass
        return response

    return transport, captured


def _failing_groq(exception_factory):
    def transport(_request, _timeout):  # noqa: ARG001
        raise exception_factory()

    return transport


# ---------------------------------------------------------------------------
# 1. Pure helpers — prompt builder (no DB, no network)
# ---------------------------------------------------------------------------


class ProceduralPromptBuilderTests(unittest.TestCase):
    """``build_messages`` produces the right three-message envelope."""

    def test_chapter_zero_has_no_choice_acknowledgement(self) -> None:
        msgs = build_messages(
            story_seed="Tu ieved Rīgā.",
            chapters=[],
            last_choice_label=None,
            next_chapter_index=0,
        )
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["system", "system", "user"])
        self.assertIn("Latvian", msgs[0]["content"])
        # The state block must carry the seed.
        self.assertIn("Tu ieved Rīgā.", msgs[1]["content"])
        # The user block must NOT claim a previous choice on chapter 0.
        self.assertNotIn("learner just chose", msgs[2]["content"])
        # And it must request chapter 0 explicitly.
        self.assertIn("chapter 0", msgs[2]["content"])

    def test_subsequent_chapter_references_last_choice(self) -> None:
        prev = StoryChapter(
            index=0,
            narrative="Tu ieved Rīgā.",
            choices=[
                ChoiceOption(id="A", label="Tu meklē kafejnīcu."),
                ChoiceOption(id="B", label="Tu kāp autobusā."),
            ],
            selected_choice_id="B",
            selected_choice_label="Tu kāp autobusā.",
            created_at="2026-05-24T12:00:00Z",
        )
        msgs = build_messages(
            story_seed="Tu ieved Rīgā.",
            chapters=[prev],
            last_choice_label="Tu kāp autobusā.",
            next_chapter_index=1,
        )
        # The user block must reference the chosen branch verbatim.
        user_block = msgs[2]["content"]
        self.assertIn("Tu kāp autobusā.", user_block)
        self.assertIn("chapter 1", user_block)
        # The state block must reflect the chosen branch.
        self.assertIn("learner chose: Tu kāp autobusā.", msgs[1]["content"])

    def test_history_trim_keeps_only_last_chapters(self) -> None:
        """Way more than MAX_HISTORY_CHAPTERS — older ones must be elided."""

        many = []
        for index in range(20):
            many.append(
                StoryChapter(
                    index=index,
                    narrative=f"Nodaļa {index}.",
                    choices=[
                        ChoiceOption(id="A", label=f"Izvēle A nodaļā {index}."),
                        ChoiceOption(id="B", label=f"Izvēle B nodaļā {index}."),
                    ],
                    selected_choice_id="A",
                    selected_choice_label=f"Izvēle A nodaļā {index}.",
                )
            )
        msgs = build_messages(
            story_seed="Tu sāc.",
            chapters=many,
            last_choice_label="Izvēle A nodaļā 19.",
            next_chapter_index=20,
        )
        state_block = msgs[1]["content"]
        # Oldest chapters must be gone.
        self.assertNotIn("Nodaļa 0.", state_block)
        self.assertNotIn("Nodaļa 5.", state_block)
        # Most-recent ones must be present.
        self.assertIn("Nodaļa 19.", state_block)


# ---------------------------------------------------------------------------
# 2. Persistence / state shape (against a tempfile SQLite DB)
# ---------------------------------------------------------------------------


class ProceduralStateTests(unittest.TestCase):
    """``load_state`` / ``reset_state`` round-trip through the DB."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        story_service._reset_procedural_story_ddl_cache()
        server.init_auth_store()
        story_service.ensure_procedural_story_tables_ready()
        self.env_patch = patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "50",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "30",
                "AI_SCORING_DAILY_REQUEST_LIMIT_PRO": "60",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        story_service._reset_procedural_story_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_brand_new_account_has_empty_state(self) -> None:
        state = load_state("acct_new")
        self.assertEqual(state.account_id, "acct_new")
        self.assertEqual(state.story_seed, "")
        self.assertEqual(state.chapter_index, 0)
        self.assertEqual(state.chapters, [])
        self.assertFalse(state.pending_choice)
        self.assertFalse(state.is_finished)

    def test_load_state_requires_account_id(self) -> None:
        with self.assertRaises(ProceduralStoryInvalidRequest):
            load_state("")

    def test_reset_state_is_idempotent_for_unknown_account(self) -> None:
        reset_state("acct_unknown")  # no row — must not raise
        self.assertEqual(load_state("acct_unknown").chapters, [])

    def test_first_chapter_persists_seed_and_increments_index(self) -> None:
        result = generate_chapter(
            account_id="acct_first",
            plan="free",
            raw_body={"seed": "Tu esi Vecrīgā."},
            transport=lambda r, t: _make_groq_response(
                "Vecrīga ir skaista no rīta.",
                [
                    {"id": "A", "label": "Tu ej uz Doma laukumu."},
                    {"id": "B", "label": "Tu meklē kafejnīcu."},
                ],
            ),
        )
        self.assertEqual(result.chapter.index, 0)
        self.assertEqual(result.state.chapter_index, 1)
        self.assertEqual(result.state.story_seed, "Tu esi Vecrīgā.")
        self.assertTrue(result.state.pending_choice)
        self.assertEqual(len(result.chapter.choices), 2)
        self.assertEqual(result.chapter.choices[0].id, "A")
        # Persisted in the DB.
        reloaded = load_state("acct_first")
        self.assertEqual(reloaded.chapter_index, 1)
        self.assertEqual(len(reloaded.chapters), 1)
        self.assertEqual(reloaded.chapters[0].narrative, "Vecrīga ir skaista no rīta.")

    def test_two_accounts_do_not_share_state(self) -> None:
        generate_chapter(
            account_id="acct_alice",
            plan="free",
            raw_body={"seed": "Alise sāk savu ceļojumu."},
            transport=lambda r, t: _make_groq_response("Alisei ir saulains rīts."),
        )
        generate_chapter(
            account_id="acct_bob",
            plan="free",
            raw_body={"seed": "Bobs sāk savu ceļojumu."},
            transport=lambda r, t: _make_groq_response("Bobs sēž kafejnīcā."),
        )
        alice = load_state("acct_alice")
        bob = load_state("acct_bob")
        self.assertEqual(alice.story_seed, "Alise sāk savu ceļojumu.")
        self.assertEqual(bob.story_seed, "Bobs sāk savu ceļojumu.")
        self.assertIn("Alisei", alice.chapters[0].narrative)
        self.assertNotIn("Bobs", alice.chapters[0].narrative)

    def test_corrupt_history_row_recovers_to_empty(self) -> None:
        # Simulate a corrupt JSON blob landing in the persisted column.
        from server_app.core import db_connection

        with db_connection() as conn:
            story_service._ensure_procedural_stories_table(conn)
            conn.execute(
                """
                INSERT INTO procedural_stories
                    (account_id, story_seed, chapter_index, history, last_updated)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("acct_corrupt", "seed", 3, "{not valid json", "2026-05-24T12:00:00Z"),
            )
            conn.commit()
        state = load_state("acct_corrupt")
        # Row exists so seed survives, but chapters fall back to [].
        self.assertEqual(state.story_seed, "seed")
        self.assertEqual(state.chapters, [])


# ---------------------------------------------------------------------------
# 3. End-to-end chapter generation (mocked Groq + tempfile DB)
# ---------------------------------------------------------------------------


class ProceduralChapterGenerationTests(unittest.TestCase):
    """Full ``generate_chapter`` flow with a scripted transport."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        story_service._reset_procedural_story_ddl_cache()
        server.init_auth_store()
        story_service.ensure_procedural_story_tables_ready()
        self.env_patch = patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "50",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "30",
                "AI_SCORING_DAILY_REQUEST_LIMIT_PRO": "60",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        story_service._reset_procedural_story_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_quota_tracked_through_response(self) -> None:
        result = generate_chapter(
            account_id="acct_quota",
            plan="free",
            raw_body={},
            transport=lambda r, t: _make_groq_response("Nodaļa viens."),
        )
        self.assertEqual(result.quota["used"], 1)
        self.assertGreater(result.quota["limit"], 0)

    def test_pending_choice_blocks_next_chapter_without_choice_id(self) -> None:
        generate_chapter(
            account_id="acct_pending",
            plan="free",
            raw_body={},
            transport=lambda r, t: _make_groq_response("Nodaļa nulle."),
        )
        with self.assertRaises(ProceduralStoryInvalidRequest) as ctx:
            generate_chapter(
                account_id="acct_pending",
                plan="free",
                raw_body={},  # missing choice_id
                transport=lambda r, t: _make_groq_response("Nodaļa viens."),
            )
        self.assertIn("choice_id", str(ctx.exception))

    def test_invalid_choice_id_raises_typed_error(self) -> None:
        generate_chapter(
            account_id="acct_invalid",
            plan="free",
            raw_body={},
            transport=lambda r, t: _make_groq_response(
                "Nodaļa nulle.",
                [
                    {"id": "A", "label": "Aiziet."},
                    {"id": "B", "label": "Palikt."},
                ],
            ),
        )
        with self.assertRaises(ProceduralStoryInvalidRequest):
            generate_chapter(
                account_id="acct_invalid",
                plan="free",
                raw_body={"choice_id": "Z"},  # not in the choices
                transport=lambda r, t: _make_groq_response("Nodaļa viens."),
            )

    def test_provider_failure_refunds_quota_slot(self) -> None:
        before = quota_service.AIQuotaLedger().current_usage("acct_refund", "free")
        with self.assertRaises(ProceduralStoryProviderError):
            generate_chapter(
                account_id="acct_refund",
                plan="free",
                raw_body={},
                transport=_failing_groq(
                    lambda: ProceduralStoryProviderError("simulated outage")
                ),
            )
        after = quota_service.AIQuotaLedger().current_usage("acct_refund", "free")
        self.assertEqual(after, before, "quota slot was not refunded on failure")

    def test_invalid_llm_output_raises_provider_error(self) -> None:
        """The model returned narrative but only one choice — fail loudly."""

        bad_response = {
            "model": "llama-3.3-70b-versatile",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "narrative": "Tikai viena izvēle.",
                                "choices": [{"id": "A", "label": "Vienīgā."}],
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }
        with self.assertRaises(ProceduralStoryProviderError):
            generate_chapter(
                account_id="acct_bad_llm",
                plan="free",
                raw_body={},
                transport=lambda r, t: bad_response,
            )

    def test_reset_wipes_existing_story(self) -> None:
        generate_chapter(
            account_id="acct_reset",
            plan="free",
            raw_body={"seed": "First story."},
            transport=lambda r, t: _make_groq_response("Pirmais sākums."),
        )
        result = generate_chapter(
            account_id="acct_reset",
            plan="free",
            raw_body={"reset": True, "seed": "Second story."},
            transport=lambda r, t: _make_groq_response("Otrais sākums."),
        )
        # After reset, chapter_index restarts at 0 and the new seed wins.
        self.assertEqual(result.chapter.index, 0)
        self.assertEqual(result.state.chapter_index, 1)
        self.assertEqual(result.state.story_seed, "Second story.")
        self.assertEqual(len(result.state.chapters), 1)
        self.assertEqual(result.state.chapters[0].narrative, "Otrais sākums.")


# ---------------------------------------------------------------------------
# 4. Branching state — distinct choices produce distinct paths
# ---------------------------------------------------------------------------


class ProceduralBranchingTests(unittest.TestCase):
    """Choosing different branches must produce divergent story states."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        story_service._reset_procedural_story_ddl_cache()
        server.init_auth_store()
        story_service.ensure_procedural_story_tables_ready()
        self.env_patch = patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "50",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "30",
                "AI_SCORING_DAILY_REQUEST_LIMIT_PRO": "60",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        story_service._reset_procedural_story_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def _shared_chapter_zero(self):
        return _make_groq_response(
            "Tu sēdi pieturā un gaidi autobusu.",
            [
                {"id": "A", "label": "Tu sāc runāt ar kaimiņieni."},
                {"id": "B", "label": "Tu klusē un skaties pa logu."},
            ],
        )

    def test_distinct_choices_diverge_into_distinct_paths(self) -> None:
        """Branch A and branch B from the same seed land in different states."""

        # Account 1 picks A.
        generate_chapter(
            account_id="acct_branchA",
            plan="free",
            raw_body={"seed": "Tu esi autobusa pieturā."},
            transport=lambda r, t: self._shared_chapter_zero(),
        )
        generate_chapter(
            account_id="acct_branchA",
            plan="free",
            raw_body={"choice_id": "A"},
            transport=lambda r, t: _make_groq_response(
                "Kaimiņiene smaida un atbild laipni.",
                [
                    {"id": "A", "label": "Tu jautā par laiku."},
                    {"id": "B", "label": "Tu jautā par autobusu."},
                ],
            ),
        )

        # Account 2 picks B.
        generate_chapter(
            account_id="acct_branchB",
            plan="free",
            raw_body={"seed": "Tu esi autobusa pieturā."},
            transport=lambda r, t: self._shared_chapter_zero(),
        )
        generate_chapter(
            account_id="acct_branchB",
            plan="free",
            raw_body={"choice_id": "B"},
            transport=lambda r, t: _make_groq_response(
                "Tu vēro lapas, kas kustas vējā.",
                [
                    {"id": "A", "label": "Tu noliec galvu uz leju."},
                    {"id": "B", "label": "Tu skaties debesīs."},
                ],
            ),
        )

        a_state = load_state("acct_branchA")
        b_state = load_state("acct_branchB")
        # Both finished chapter 0 with a selected choice + a chapter 1 pending.
        self.assertEqual(a_state.chapter_index, 2)
        self.assertEqual(b_state.chapter_index, 2)
        self.assertEqual(a_state.chapters[0].selected_choice_id, "A")
        self.assertEqual(b_state.chapters[0].selected_choice_id, "B")
        # The chapter-1 narratives diverge — that's the branch.
        self.assertNotEqual(
            a_state.chapters[1].narrative,
            b_state.chapters[1].narrative,
        )
        self.assertIn("Kaimiņiene", a_state.chapters[1].narrative)
        self.assertIn("vēro", b_state.chapters[1].narrative)


# ---------------------------------------------------------------------------
# 5. Coherence — chapter N's prompt MUST mention the previous choice
# ---------------------------------------------------------------------------


class ProceduralCoherenceTests(unittest.TestCase):
    """The strongest signal that the narrative honours branching.

    Mock Groq, capture the request body sent to it for chapter 1, and
    assert that the previous chapter's selected choice label appears
    inside the messages that go to the LLM. If that assertion is true,
    we can rely on a competent model to actually reference the choice
    in the narrative.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        story_service._reset_procedural_story_ddl_cache()
        server.init_auth_store()
        story_service.ensure_procedural_story_tables_ready()
        self.env_patch = patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "50",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "30",
                "AI_SCORING_DAILY_REQUEST_LIMIT_PRO": "60",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        story_service._reset_procedural_story_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_chapter_one_prompt_mentions_previous_choice(self) -> None:
        # Chapter 0: setup with a unique, identifiable choice label.
        chosen_label = "Tu nopērc piparkūku ar krējumu."
        chapter_zero = _make_groq_response(
            "Tu ej ar maiņās gaisu uz nelielo veikalu.",
            [
                {"id": "A", "label": chosen_label},
                {"id": "B", "label": "Tu paej garām."},
            ],
        )
        generate_chapter(
            account_id="acct_coherence",
            plan="free",
            raw_body={"seed": "Tu esi Latgales tirgū."},
            transport=lambda r, t: chapter_zero,
        )

        # Chapter 1: capture the LLM input, assert it mentions the choice.
        chapter_one_response = _make_groq_response(
            "Piparkūka ir tieši tāda, kā atceries no bērnības.",
            [
                {"id": "A", "label": "Tu ēd to uzreiz."},
                {"id": "B", "label": "Tu glabā vēlākam."},
            ],
        )
        capture_transport, captured = _capturing_groq(chapter_one_response)
        generate_chapter(
            account_id="acct_coherence",
            plan="free",
            raw_body={"choice_id": "A"},
            transport=capture_transport,
        )

        # The Groq payload must carry messages.
        msgs = captured.get("messages") or []
        self.assertGreaterEqual(len(msgs), 3)
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles[0], "system")
        self.assertEqual(roles[-1], "user")
        # Strongest assertion: the selected label appears in the
        # outbound messages (either the state block or the user block).
        joined = "\n".join(m["content"] for m in msgs)
        self.assertIn(
            chosen_label,
            joined,
            "Chapter 1 prompt must reference the previously selected choice "
            f"label ({chosen_label!r}) — otherwise the story can drift.",
        )
        # And the system prompt is the procedural-story persona.
        self.assertEqual(msgs[0]["content"], PROCEDURAL_SYSTEM_PROMPT)

    def test_multi_step_coherence_chain(self) -> None:
        """Three chapters in a row — each prompt mentions the *previous* choice."""

        labels = {
            0: "Tu ej uz krastmalu.",
            1: "Tu apsēdies uz sola.",
        }
        # Pre-seed chapter 0 and chapter 1, capturing both LLM calls.
        ch0 = _make_groq_response(
            "Pavasara rīts Rīgā.",
            [
                {"id": "A", "label": labels[0]},
                {"id": "B", "label": "Tu paliec mājās."},
            ],
        )
        ch1 = _make_groq_response(
            "Vējš pūš no jūras puses.",
            [
                {"id": "A", "label": labels[1]},
                {"id": "B", "label": "Tu turpini iet."},
            ],
        )
        ch2 = _make_groq_response(
            "Tu redzi kaiju, kas peld pa Daugavu.",
            [
                {"id": "A", "label": "Tu paliec sēdam."},
                {"id": "B", "label": "Tu celies un dodies prom."},
            ],
        )
        seq, _ = _scripted_groq(ch0)
        generate_chapter(
            account_id="acct_chain",
            plan="free",
            raw_body={"seed": "Tu pamostis svētdien."},
            transport=seq,
        )

        # Chapter 1 with capture — must mention chapter-0 choice.
        cap1_transport, cap1 = _capturing_groq(ch1)
        generate_chapter(
            account_id="acct_chain",
            plan="free",
            raw_body={"choice_id": "A"},
            transport=cap1_transport,
        )
        joined1 = "\n".join(m["content"] for m in cap1.get("messages", []))
        self.assertIn(labels[0], joined1)

        # Chapter 2 with capture — must mention chapter-1 choice.
        cap2_transport, cap2 = _capturing_groq(ch2)
        generate_chapter(
            account_id="acct_chain",
            plan="free",
            raw_body={"choice_id": "A"},
            transport=cap2_transport,
        )
        joined2 = "\n".join(m["content"] for m in cap2.get("messages", []))
        self.assertIn(labels[1], joined2)


# ---------------------------------------------------------------------------
# 6. Quota exhaustion + cap on chapter count
# ---------------------------------------------------------------------------


class ProceduralQuotaAndCapTests(unittest.TestCase):
    """Story length cap + daily quota integration."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        quota_service._reset_ledger_ddl_cache()
        story_service._reset_procedural_story_ddl_cache()
        server.init_auth_store()
        story_service.ensure_procedural_story_tables_ready()

    def tearDown(self) -> None:
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        story_service._reset_procedural_story_ddl_cache()
        quota_service._reset_ledger_ddl_cache()

    def test_quota_exhaustion_raises(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LVCODEX_AI_DAILY_LIMIT": "100",
                "AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "1",
            },
            clear=False,
        ):
            generate_chapter(
                account_id="acct_q",
                plan="free",
                raw_body={"seed": "First."},
                transport=lambda r, t: _make_groq_response("Nodaļa nulle."),
            )
            with self.assertRaises(QuotaExceededError):
                generate_chapter(
                    account_id="acct_q",
                    plan="free",
                    raw_body={"choice_id": "A"},
                    transport=lambda r, t: _make_groq_response("Nodaļa viens."),
                )

    def test_story_finished_after_max_chapters(self) -> None:
        """Manually push chapter_index past the cap, then verify the guard."""

        from server_app.core import db_connection

        # Insert a row that already has the maximum count — generate
        # should reject with ProceduralStoryFinished.
        with db_connection() as conn:
            story_service._ensure_procedural_stories_table(conn)
            conn.execute(
                """
                INSERT INTO procedural_stories
                    (account_id, story_seed, chapter_index, history, last_updated)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "acct_cap",
                    "seed",
                    MAX_CHAPTERS_PER_STORY,
                    "[]",
                    "2026-05-24T12:00:00Z",
                ),
            )
            conn.commit()
        with patch.dict(
            os.environ, {"AI_SCORING_DAILY_REQUEST_LIMIT_FREE": "10"}, clear=False
        ):
            with self.assertRaises(ProceduralStoryFinished):
                generate_chapter(
                    account_id="acct_cap",
                    plan="free",
                    raw_body={},
                    transport=lambda r, t: _make_groq_response("never"),
                )


if __name__ == "__main__":
    unittest.main()
