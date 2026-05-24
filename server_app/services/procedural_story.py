"""T-055 — Procedural choose-your-own-adventure story generator.

The procedural story engine produces a branching narrative chapter
per request using Groq (``llama-3.3-70b-versatile``). Unlike T-053
(:mod:`server_app.services.companion`) which is a free-form chat
surface with a rolling memory blob, this service generates **discrete
chapters** with **explicit branching choices** that the learner picks
between. Each chapter carries forward the previous choices so the story
is *coherent* — chapter N's prompt references the learner's last 1-3
selected choices verbatim so the model cannot ignore them.

State model
-----------

Per-user state is persisted in the ``procedural_stories`` table (one row
per ``account_id``)::

    account_id          TEXT PRIMARY KEY
    story_seed          TEXT NOT NULL             -- one-line setup line
    chapter_index       INTEGER NOT NULL DEFAULT 0
    history             TEXT NOT NULL DEFAULT '[]' -- JSON list of chapter records
    last_updated        TEXT NOT NULL

The ``history`` JSON shape::

    [
      {
        "index": 0,
        "narrative": "<Latvian prose, ≤ 3 sentences>",
        "choices": [{"id": "A", "label": "..."}, ...],
        "selected_choice_id": "A" | null,
        "selected_choice_label": "...",
        "created_at": "2026-05-24T..."
      },
      ...
    ]

When a chapter has not yet been "answered" (the learner has not picked
a choice), ``selected_choice_id`` is ``null`` and the next call to
:func:`generate_chapter` requires a ``choice_id`` so the engine knows
which branch to follow.

Design notes vs. T-053
----------------------

T-053 keeps a *free-form text summary*; T-055 keeps a *structured
chapter ledger*. The ledger is bounded (we keep the last
:data:`MAX_HISTORY_CHAPTERS` chapters in the prompt context — older
chapters are still on disk but elided from the LLM call) so prompt cost
is predictable as the story grows. The full history stays in the row
for the UI's "previous chapters" panel.

The generator reuses :func:`server_app.services.npc.call_groq_chat` for
the actual HTTP plumbing (retries, 429, model env-config) — exactly the
same playbook as T-053 / T-045.

Tables
------

``procedural_stories`` (one row per learner). DDL is ANSI-compatible so
it ports cleanly to Postgres after T-021.

Tests in ``tests/server/test_procedural_story.py`` cover:

  * chapter generation with mocked transport (no network)
  * branching state — choosing different ids advances the story
    along distinct branches
  * coherence — chapter N's prompt mentions the previous choices
    (the strongest signal that the narrative stays consistent)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional
import urllib.request

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from server_app.core import db_connection
from server_app.services.npc import (
    NPCProviderError,
    call_groq_chat,
)
from server_app.services.quota import (
    AIQuotaLedger,
    QuotaExceededError,
    reserve_daily_ai_quota,
)


logger = logging.getLogger("lvcodex.procedural_story")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Maximum number of *prior* chapters fed back into the model prompt.
# Older chapters remain in the persisted history (for the UI) but are
# elided from the LLM call so prompt cost stays bounded as the story
# accumulates many chapters.
MAX_HISTORY_CHAPTERS = 5

# Hard ceilings on user-supplied / model-supplied text. These exist to
# bound the prompt budget and protect the persisted row from runaway
# payloads.
MAX_NARRATIVE_CHARS = 800
MAX_CHOICE_LABEL_CHARS = 120
MAX_CHOICE_ID_CHARS = 8
MIN_CHOICES = 2
MAX_CHOICES = 4
MAX_HISTORY_ROW_BYTES = 16_384  # 16 KB hard cap on the persisted JSON

PROCEDURAL_DEFAULT_TEMPERATURE = 0.8
PROCEDURAL_DEFAULT_MAX_TOKENS = 380

# Story is over after this many chapters (defensive cap — prevents an
# infinite series and lets the UI render an "epilogue" button).
MAX_CHAPTERS_PER_STORY = 12

# Seed pool used when the learner doesn't supply one. The model is told
# to set the scene in one short sentence so the *first* chapter has
# something concrete to riff on.
DEFAULT_SEEDS_LV: list[str] = [
    "Tu ieved Rīgas Centrālajā stacijā agri no rīta.",
    "Tu sēdi kafejnīcā Vecrīgā un gaidi draugu.",
    "Tu staigā pa Jūrmalas pludmali rudens vakarā.",
    "Tu esi tikko atvēris durvis savai jaunajai dzīvoklim.",
    "Tu ej uz darbu un satiec kaimiņu kāpņutelpā.",
]


_DDL_LOCK = threading.Lock()
_DDL_APPLIED = False


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProceduralStoryError(Exception):
    """Base class for procedural-story service errors."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProceduralStoryInvalidRequest(ProceduralStoryError):
    status_code = 400


class ProceduralStoryProviderError(ProceduralStoryError):
    status_code = 502


class ProceduralStoryFinished(ProceduralStoryError):
    """Raised when the learner tries to generate past the story cap."""

    status_code = 409


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ChoiceOption(BaseModel):
    """A single branching choice the learner can pick."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: str = Field(..., min_length=1, max_length=MAX_CHOICE_ID_CHARS)
    label: str = Field(..., min_length=1, max_length=MAX_CHOICE_LABEL_CHARS)


class StoryChapter(BaseModel):
    """One persisted chapter as returned to clients."""

    model_config = ConfigDict(extra="ignore")

    index: int = Field(ge=0)
    narrative: str = Field(..., min_length=1, max_length=MAX_NARRATIVE_CHARS)
    choices: list[ChoiceOption] = Field(default_factory=list)
    selected_choice_id: Optional[str] = None
    selected_choice_label: Optional[str] = None
    created_at: str = ""


class GenerateChapterRequest(BaseModel):
    """Inbound body for ``POST /api/stories/generate-chapter``."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    # When present and the learner already has a chapter pending a
    # choice, this records which branch they picked *before* the new
    # chapter is generated.
    choice_id: Optional[str] = Field(default=None, max_length=MAX_CHOICE_ID_CHARS)

    # Optional one-liner that overrides the default seed pool — only
    # honored on the very first chapter for the learner.
    seed: Optional[str] = Field(default=None, max_length=240)

    # If true, wipes the existing story before generating chapter 0.
    reset: bool = False

    @field_validator("choice_id")
    @classmethod
    def _strip_choice_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class StoryStateSnapshot(BaseModel):
    """``GET /api/stories/state`` / response of generate."""

    model_config = ConfigDict(extra="ignore")

    account_id: str
    story_seed: str
    chapter_index: int = Field(ge=0)
    chapters: list[StoryChapter] = Field(default_factory=list)
    pending_choice: bool = False
    is_finished: bool = False
    last_updated: str = ""


class GenerateChapterResponse(BaseModel):
    """Outbound body for ``POST /api/stories/generate-chapter``."""

    model_config = ConfigDict(extra="ignore")

    chapter: StoryChapter
    state: StoryStateSnapshot
    quota: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


def _ensure_procedural_stories_table(conn: sqlite3.Connection) -> None:
    """Create the ``procedural_stories`` table if missing.

    ANSI-compatible DDL so the same migration runs on SQLite (today)
    and Postgres (after T-021).
    """

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS procedural_stories (
            account_id TEXT PRIMARY KEY,
            story_seed TEXT NOT NULL DEFAULT '',
            chapter_index INTEGER NOT NULL DEFAULT 0,
            history TEXT NOT NULL DEFAULT '[]',
            last_updated TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_procedural_stories_updated
            ON procedural_stories(last_updated);
        """
    )


def ensure_procedural_story_tables_ready() -> None:
    """Idempotent DDL initialiser. Cheap to call repeatedly."""

    global _DDL_APPLIED
    if _DDL_APPLIED:
        return
    with _DDL_LOCK:
        if _DDL_APPLIED:
            return
        with db_connection() as conn:
            _ensure_procedural_stories_table(conn)
        _DDL_APPLIED = True


def _reset_procedural_story_ddl_cache() -> None:
    """Test hook — re-run the DDL for a fresh tempfile DB."""

    global _DDL_APPLIED
    with _DDL_LOCK:
        _DDL_APPLIED = False


def _now_iso(now: Optional[datetime] = None) -> str:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Seed selection
# ---------------------------------------------------------------------------


def _deterministic_seed(account_id: str) -> str:
    """Pick a seed from :data:`DEFAULT_SEEDS_LV` deterministically.

    Using a stable hash of the account id guarantees:
        * the same learner sees the same opening line on repeated resets
          (until they pass an explicit ``seed`` override), which keeps
          the UX predictable;
        * different learners spread evenly across seeds without the
          server needing to import :mod:`random` (the seeds are part of
          the public surface — they go into the LLM prompt).
    """

    if not DEFAULT_SEEDS_LV:
        return "Tu sāc savu Latvijas piedzīvojumu."
    key = (account_id or "anon").encode("utf-8")
    digest = 0
    for byte in key:
        digest = (digest * 131 + byte) & 0xFFFFFFFF
    return DEFAULT_SEEDS_LV[digest % len(DEFAULT_SEEDS_LV)]


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def _load_row(account_id: str) -> Optional[dict[str, Any]]:
    """Return the raw row (no JSON decoding) for ``account_id``."""

    ensure_procedural_story_tables_ready()
    with db_connection() as conn:
        _ensure_procedural_stories_table(conn)
        row = conn.execute(
            """
            SELECT account_id, story_seed, chapter_index, history, last_updated
            FROM procedural_stories
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "account_id": row["account_id"],
        "story_seed": row["story_seed"] or "",
        "chapter_index": int(row["chapter_index"] or 0),
        "history": row["history"] or "[]",
        "last_updated": row["last_updated"] or "",
    }


def _decode_history(raw: str) -> list[dict[str, Any]]:
    """Parse the persisted ``history`` JSON, returning a list.

    Tolerates a corrupt row by returning an empty list — the worst-case
    UX is "your previous chapters are gone" rather than "you cannot
    use the feature at all", which matches T-053's defensive posture.
    """

    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("procedural_story_history_corrupt")
        return []
    if not isinstance(decoded, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        cleaned.append(entry)
    return cleaned


def load_state(account_id: str) -> StoryStateSnapshot:
    """Return the current story state for ``account_id``.

    Brand-new learners get an empty state (no chapters, no seed) — the
    seed is chosen at chapter-0 generation time so we don't show a
    "story already started" indicator until the learner actually
    advances.
    """

    if not account_id:
        raise ProceduralStoryInvalidRequest("account_id is required.")
    row = _load_row(account_id)
    if row is None:
        return StoryStateSnapshot(
            account_id=account_id,
            story_seed="",
            chapter_index=0,
            chapters=[],
            pending_choice=False,
            is_finished=False,
            last_updated="",
        )
    history = _decode_history(row["history"])
    chapters = [_coerce_chapter(c) for c in history]
    pending = bool(chapters and chapters[-1].selected_choice_id is None)
    is_finished = row["chapter_index"] >= MAX_CHAPTERS_PER_STORY
    return StoryStateSnapshot(
        account_id=account_id,
        story_seed=row["story_seed"],
        chapter_index=row["chapter_index"],
        chapters=chapters,
        pending_choice=pending,
        is_finished=is_finished,
        last_updated=row["last_updated"],
    )


def _coerce_chapter(entry: dict[str, Any]) -> StoryChapter:
    """Best-effort conversion of a persisted entry into a StoryChapter."""

    choices_raw = entry.get("choices") or []
    choices: list[ChoiceOption] = []
    if isinstance(choices_raw, list):
        for choice in choices_raw:
            if isinstance(choice, dict):
                cid = str(choice.get("id") or "").strip()[:MAX_CHOICE_ID_CHARS]
                label = str(choice.get("label") or "").strip()[:MAX_CHOICE_LABEL_CHARS]
                if cid and label:
                    choices.append(ChoiceOption(id=cid, label=label))
    return StoryChapter(
        index=int(entry.get("index") or 0),
        narrative=str(entry.get("narrative") or "")[:MAX_NARRATIVE_CHARS] or "(missing)",
        choices=choices,
        selected_choice_id=(entry.get("selected_choice_id") or None) or None,
        selected_choice_label=(entry.get("selected_choice_label") or None) or None,
        created_at=str(entry.get("created_at") or ""),
    )


def _write_state(
    account_id: str,
    story_seed: str,
    chapter_index: int,
    history: list[dict[str, Any]],
    now: Optional[datetime] = None,
) -> str:
    """Persist the new state, returning the ISO timestamp written.

    Enforces the :data:`MAX_HISTORY_ROW_BYTES` cap by dropping the
    *oldest* chapters until the JSON blob fits. The UI keeps showing the
    chapters that survive — older chapters fall off the screen quietly,
    matching the behaviour of T-053's front-bias memory trim.
    """

    ensure_procedural_story_tables_ready()
    now_iso = _now_iso(now)
    encoded = json.dumps(history, ensure_ascii=False)
    while len(encoded.encode("utf-8")) > MAX_HISTORY_ROW_BYTES and len(history) > 1:
        history = history[1:]
        encoded = json.dumps(history, ensure_ascii=False)
    with db_connection() as conn:
        _ensure_procedural_stories_table(conn)
        conn.execute(
            """
            INSERT INTO procedural_stories (account_id, story_seed, chapter_index, history, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE
                SET story_seed = excluded.story_seed,
                    chapter_index = excluded.chapter_index,
                    history = excluded.history,
                    last_updated = excluded.last_updated
            """,
            (account_id, story_seed, chapter_index, encoded, now_iso),
        )
        conn.commit()
    return now_iso


def reset_state(account_id: str) -> None:
    """Wipe any existing story for ``account_id``.

    Used by ``reset=True`` on the generate route. Idempotent — a
    no-op for learners who have never started a story.
    """

    if not account_id:
        raise ProceduralStoryInvalidRequest("account_id is required.")
    ensure_procedural_story_tables_ready()
    with db_connection() as conn:
        _ensure_procedural_stories_table(conn)
        conn.execute(
            "DELETE FROM procedural_stories WHERE account_id = ?",
            (account_id,),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


PROCEDURAL_SYSTEM_PROMPT = (
    "You are a Latvian-language interactive-fiction author for an A2 learner. "
    "Each turn, produce ONE short chapter (≤ 3 simple Latvian sentences) that "
    "continues the running story. Then offer 2-3 distinct branching choices "
    "the learner can pick from. Each choice must be a single short Latvian "
    "sentence the learner could realistically say or do next. The narrative "
    "MUST acknowledge the learner's most recent previous choice when one is "
    "provided. Stay at A2 vocabulary (everyday situations: home, work, "
    "shopping, travel). Output VALID JSON ONLY, no markdown, with the schema: "
    '{"narrative": "<Latvian prose>", "choices": [{"id": "A", "label": "<Latvian>"}, ...]}'
)


def _history_for_prompt(
    chapters: list[StoryChapter],
    *,
    limit: int = MAX_HISTORY_CHAPTERS,
) -> str:
    """Render the recent chapters into a plain-text block for the LLM.

    We emit each chapter as ``"Chapter N: <narrative> -> chose: <label>"``
    so the model can re-read its own past output without parsing a
    nested structure. Older chapters beyond ``limit`` are elided to
    bound the prompt cost.
    """

    if not chapters:
        return "(no prior chapters — this is chapter 0)"
    tail = chapters[-limit:] if limit > 0 else chapters
    lines: list[str] = []
    for ch in tail:
        choice = ch.selected_choice_label or "(no choice yet)"
        lines.append(
            f"Chapter {ch.index}: {ch.narrative.strip()} -> learner chose: {choice}"
        )
    return "\n".join(lines)


def build_messages(
    story_seed: str,
    chapters: list[StoryChapter],
    last_choice_label: Optional[str],
    next_chapter_index: int,
) -> list[dict[str, str]]:
    """Compose the LLM messages array for the next chapter.

    Shape: ``[system-persona, system-state, user]``. The user message is
    a small instruction that tells the model which chapter index to
    produce and which branch was just chosen — both of which the model
    *must* honour for the coherence test to pass.
    """

    history_block = _history_for_prompt(chapters)
    seed_line = story_seed.strip() or "Tu sāc savu Latvijas piedzīvojumu."
    state_block = (
        f"Story seed (chapter 0 setting): {seed_line}\n"
        f"Previous chapters (oldest first):\n{history_block}"
    )
    if last_choice_label:
        user_block = (
            f"The learner just chose: \"{last_choice_label}\".\n"
            f"Write chapter {next_chapter_index}. Acknowledge that choice in the "
            f"first sentence of the narrative, then offer 2-3 new branching choices."
        )
    else:
        user_block = (
            f"Write chapter {next_chapter_index} — the opening. "
            "Set the scene using the story seed above in one short sentence, "
            "then offer 2-3 branching choices the learner can pick from."
        )

    return [
        {"role": "system", "content": PROCEDURAL_SYSTEM_PROMPT},
        {"role": "system", "content": state_block},
        {"role": "user", "content": user_block},
    ]


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------


def _parse_llm_chapter(raw_content: str) -> tuple[str, list[ChoiceOption]]:
    """Parse the model's JSON output into ``(narrative, choices)``.

    The system prompt asks for JSON-only output, but real models
    occasionally wrap it in code fences or trailing prose. We strip the
    most common offenders before raising.
    """

    content = (raw_content or "").strip()
    if not content:
        raise ProceduralStoryProviderError("Story generator returned empty content.", status_code=502)
    # Strip ```json … ``` fences if present.
    if content.startswith("```"):
        # Drop first fence line
        first_nl = content.find("\n")
        if first_nl > 0:
            content = content[first_nl + 1:]
        if content.endswith("```"):
            content = content[: -3]
        content = content.strip()
    # Find the outer JSON object if the model added prose around it.
    if not content.startswith("{"):
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            content = content[first_brace : last_brace + 1]
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError) as error:
        raise ProceduralStoryProviderError(
            f"Story generator returned non-JSON output: {error}",
            status_code=502,
        ) from error
    if not isinstance(parsed, dict):
        raise ProceduralStoryProviderError("Story generator output is not a JSON object.", status_code=502)
    narrative = str(parsed.get("narrative") or "").strip()
    if not narrative:
        raise ProceduralStoryProviderError("Story generator returned an empty narrative.", status_code=502)
    if len(narrative) > MAX_NARRATIVE_CHARS:
        narrative = narrative[: MAX_NARRATIVE_CHARS].rstrip()
    raw_choices = parsed.get("choices") or []
    if not isinstance(raw_choices, list) or len(raw_choices) < MIN_CHOICES:
        raise ProceduralStoryProviderError(
            f"Story generator returned fewer than {MIN_CHOICES} choices.",
            status_code=502,
        )
    choices: list[ChoiceOption] = []
    seen_ids: set[str] = set()
    fallback_letters = ["A", "B", "C", "D"]
    for index, raw in enumerate(raw_choices[:MAX_CHOICES]):
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("id") or "").strip().upper()
        if not cid:
            cid = fallback_letters[index] if index < len(fallback_letters) else f"C{index}"
        cid = cid[:MAX_CHOICE_ID_CHARS]
        if cid in seen_ids:
            cid = fallback_letters[index] if index < len(fallback_letters) else f"C{index}"
        seen_ids.add(cid)
        label = str(raw.get("label") or "").strip()
        if not label:
            continue
        if len(label) > MAX_CHOICE_LABEL_CHARS:
            label = label[:MAX_CHOICE_LABEL_CHARS].rstrip()
        choices.append(ChoiceOption(id=cid, label=label))
    if len(choices) < MIN_CHOICES:
        raise ProceduralStoryProviderError(
            f"Story generator returned fewer than {MIN_CHOICES} valid choices.",
            status_code=502,
        )
    return narrative, choices


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def parse_generate_request(raw: Any) -> GenerateChapterRequest:
    """Pydantic-validate the inbound body."""

    try:
        return GenerateChapterRequest.model_validate(raw or {})
    except ValidationError as error:
        raise ProceduralStoryInvalidRequest(
            "Procedural-story generate request failed schema validation: "
            + str(error.errors())
        ) from error


# ---------------------------------------------------------------------------
# Choice resolution
# ---------------------------------------------------------------------------


def _apply_choice(
    chapters: list[StoryChapter],
    choice_id: str,
) -> tuple[list[StoryChapter], str]:
    """Mark the last chapter's selected choice, returning the updated list.

    Returns the label of the selected choice for use in the LLM prompt
    (the *verbatim* string the model emitted earlier, so the coherence
    contract is preserved across language quirks).
    """

    if not chapters:
        raise ProceduralStoryInvalidRequest(
            "Cannot apply a choice — no chapter exists yet."
        )
    last = chapters[-1]
    if last.selected_choice_id is not None:
        raise ProceduralStoryInvalidRequest(
            "Latest chapter already has a selected choice."
        )
    match = None
    for choice in last.choices:
        if choice.id.upper() == choice_id.upper():
            match = choice
            break
    if match is None:
        raise ProceduralStoryInvalidRequest(
            f"Choice id {choice_id!r} is not part of the latest chapter."
        )
    updated_last = last.model_copy(
        update={
            "selected_choice_id": match.id,
            "selected_choice_label": match.label,
        }
    )
    return chapters[:-1] + [updated_last], match.label


# ---------------------------------------------------------------------------
# High-level chapter generator
# ---------------------------------------------------------------------------


def generate_chapter(
    *,
    account_id: str,
    plan: str = "free",
    raw_body: Any = None,
    prev_state: Optional[StoryStateSnapshot] = None,
    transport: Optional[Callable[[urllib.request.Request, float], dict[str, Any]]] = None,
    quota_user_key: Optional[str] = None,
    now: Optional[datetime] = None,
) -> GenerateChapterResponse:
    """End-to-end: load state, apply choice, call LLM, persist new chapter.

    Mirrors :func:`server_app.services.companion.generate_chat_reply` so
    the route handler stays a thin shell. ``prev_state`` is an optional
    override — when supplied, it takes priority over the row in the DB
    (used by tests and by call-sites that have already loaded the row).

    On provider failure the quota slot is **refunded** so a flaky
    upstream cannot consume a learner's daily allowance.
    """

    if not account_id:
        raise ProceduralStoryInvalidRequest("account_id is required.")
    request = parse_generate_request(raw_body)
    user_key = (quota_user_key or account_id or "").strip()
    if not user_key:
        raise ProceduralStoryInvalidRequest("Cannot reserve quota: missing user identity.")

    # Optional reset wipes the row before we read it.
    if request.reset:
        reset_state(account_id)

    state = prev_state or load_state(account_id)

    if state.is_finished:
        raise ProceduralStoryFinished(
            f"Story already has {state.chapter_index} chapters — maximum is "
            f"{MAX_CHAPTERS_PER_STORY}. Reset to start a new one."
        )

    # ------------------------------------------------------------------
    # Step 1: resolve any pending choice from a *prior* chapter.
    # ------------------------------------------------------------------
    chapters = list(state.chapters)
    last_choice_label: Optional[str] = None
    if state.pending_choice:
        if not request.choice_id:
            raise ProceduralStoryInvalidRequest(
                "Latest chapter requires a choice_id before the next chapter can be generated."
            )
        chapters, last_choice_label = _apply_choice(chapters, request.choice_id)
    elif request.choice_id and chapters:
        # Best-effort: allow re-supplying a choice for the last chapter
        # even if it was already settled (idempotent retry).
        last_choice_label = chapters[-1].selected_choice_label

    # ------------------------------------------------------------------
    # Step 2: pick / re-use the seed.
    # ------------------------------------------------------------------
    story_seed = state.story_seed.strip()
    if not story_seed:
        if request.seed:
            story_seed = request.seed.strip()[:240]
        else:
            story_seed = _deterministic_seed(account_id)

    # ------------------------------------------------------------------
    # Step 3: reserve a quota slot, then call the LLM.
    # ------------------------------------------------------------------
    # ``state.chapter_index`` reflects how many chapters have been
    # generated so far, so the *next* one's index is exactly that value
    # — and after we append it we bump the counter by one.
    next_index = state.chapter_index

    quota_snapshot = reserve_daily_ai_quota(user_key, plan)

    try:
        messages = build_messages(
            story_seed=story_seed,
            chapters=chapters,
            last_choice_label=last_choice_label,
            next_chapter_index=next_index,
        )
        try:
            provider_result = call_groq_chat(
                messages,
                temperature=PROCEDURAL_DEFAULT_TEMPERATURE,
                max_tokens=PROCEDURAL_DEFAULT_MAX_TOKENS,
                transport=transport,
            )
        except NPCProviderError as error:
            raise ProceduralStoryProviderError(str(error), status_code=error.status_code) from error
        narrative, choices = _parse_llm_chapter(provider_result.get("content") or "")
        created_at = _now_iso(now)
        new_chapter = StoryChapter(
            index=next_index,
            narrative=narrative,
            choices=choices,
            selected_choice_id=None,
            selected_choice_label=None,
            created_at=created_at,
        )
        chapters.append(new_chapter)
        new_index = next_index + 1
        history_payload = [c.model_dump() for c in chapters]
        last_updated = _write_state(
            account_id,
            story_seed,
            new_index,
            history_payload,
            now=now,
        )
    except Exception:
        try:
            AIQuotaLedger().release(user_key, plan)
        except Exception:  # noqa: BLE001 — defensive
            logger.exception("procedural_story_quota_refund_failed user=%s", user_key)
        raise

    snapshot = StoryStateSnapshot(
        account_id=account_id,
        story_seed=story_seed,
        chapter_index=new_index,
        chapters=chapters,
        pending_choice=True,
        is_finished=new_index >= MAX_CHAPTERS_PER_STORY,
        last_updated=last_updated,
    )
    response = GenerateChapterResponse(
        chapter=new_chapter,
        state=snapshot,
        quota={
            "used": int(quota_snapshot["used"]),
            "limit": int(quota_snapshot["limit"]),
            "resets_at": str(quota_snapshot["resets_at"]),
        },
        usage=dict(provider_result.get("usage") or {}),
    )
    logger.info(
        "procedural_story_chapter user=%s chapter_index=%s seed=%r",
        account_id,
        new_index,
        story_seed,
    )
    return response


__all__ = [
    "ChoiceOption",
    "DEFAULT_SEEDS_LV",
    "GenerateChapterRequest",
    "GenerateChapterResponse",
    "MAX_CHAPTERS_PER_STORY",
    "MAX_CHOICES",
    "MAX_HISTORY_CHAPTERS",
    "MAX_HISTORY_ROW_BYTES",
    "MAX_NARRATIVE_CHARS",
    "MIN_CHOICES",
    "PROCEDURAL_DEFAULT_MAX_TOKENS",
    "PROCEDURAL_DEFAULT_TEMPERATURE",
    "PROCEDURAL_SYSTEM_PROMPT",
    "ProceduralStoryError",
    "ProceduralStoryFinished",
    "ProceduralStoryInvalidRequest",
    "ProceduralStoryProviderError",
    "QuotaExceededError",
    "StoryChapter",
    "StoryStateSnapshot",
    "build_messages",
    "ensure_procedural_story_tables_ready",
    "generate_chapter",
    "load_state",
    "parse_generate_request",
    "reset_state",
]
