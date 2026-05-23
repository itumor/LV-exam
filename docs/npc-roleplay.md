# AI NPC roleplay (T-045)

## Overview

The NPC roleplay surface lets a learner chat with six pre-defined Latvian-speaking characters via the Groq `llama-3.3-70b-versatile` model. It is the first AI feature shipped on top of the T-026 quota ledger + schema validation pipeline, and it doubles as the foundation for T-053 (AI tutor companion) and T-064 (multiplayer roleplay).

## Characters

The six characters live as JSON profiles under `content/npcs/`:

| ID | Name | Role | Setting |
|---|---|---|---|
| `cashier-anna` | Anna | shop cashier | Rimi supermarket, Rīga |
| `waiter-janis` | Jānis | waiter | Lido restaurant, Rīga |
| `taxi-maris` | Māris | taxi driver | Bolt taxi, Rīga |
| `doctor-agnese` | Dr. Agnese | family doctor | Rīgas poliklīnika |
| `neighbor-liga` | Līga | neighbour | Pārdaugava stairwell |
| `teacher-andris` | Andris | Latvian language teacher | Valodu skola, Rīga |

Each profile carries: `persona`, `speech_style`, `safety_rules`, `common_scenarios`, `vocabulary_focus`, and a `sample_dialogue` for documentation only. The `safety_rules` array is concatenated into the system prompt verbatim so the LLM always sees the safety guardrails.

To add a new NPC, drop a new `<id>.json` file alongside the existing six and reload the server — there is no DB migration required.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/npc` | List NPC summaries (id, name, role, location). Requires a session. |
| `GET` | `/api/npc/{npc_id}` | Return the full NPC profile (used by future tutor flows). |
| `POST` | `/api/npc/{npc_id}/turn` | Submit a learner message; receive an NPC reply + state. |

### `POST /api/npc/{npc_id}/turn`

Request body:

```json
{
  "message": "Labdien! Cik maksā maize?",
  "conversation_id": "abc123hex"
}
```

`conversation_id` is optional on the first turn — the server creates one and returns it in `state.conversation_id`. Send it back on every subsequent turn to keep the dialogue going.

Successful response (HTTP 200):

```json
{
  "reply": "Maize maksā divi eiro un piecdesmit centi.",
  "state": {
    "npc_id": "cashier-anna",
    "conversation_id": "abc123hex",
    "turn_index": 2,
    "history_length": 2,
    "quota_used": 1,
    "quota_limit": 30,
    "quota_resets_at": "2026-05-24T00:00:00Z"
  },
  "usage": {"prompt_tokens": 184, "completion_tokens": 21}
}
```

Error responses:

| Status | Code | Cause |
|---|---|---|
| 400 | `npc_invalid_request` | Pydantic validation failed (empty message, too long, etc.). |
| 401 | — | No session cookie present. |
| 404 | `npc_not_found` | `npc_id` does not match a file under `content/npcs/`. |
| 429 | `ai_quota_exceeded` | Daily AI ledger exhausted (shared with writing/speaking scoring). |
| 502 | `npc_provider_unavailable` | Groq retries exhausted; quota slot is automatically refunded. |

## Multi-user isolation

Every read and write is filtered on `account_id`. Guessing another user's `conversation_id` returns an empty history (read) or falls through to a fresh conversation (write). Coverage in `tests/server/test_npc.py::test_multi_user_isolation_other_account_cannot_read_history`.

## Cost + quota

The same `AIQuotaLedger` that gates writing/speaking scoring (T-026) gates NPC turns. The daily limit defaults to `LVCODEX_AI_DAILY_LIMIT=30` and is clamped down further by the per-plan `AI_SCORING_DAILY_REQUEST_LIMIT_<PLAN>` env vars. Token usage is returned in `usage` so T-027 cost telemetry can record it.

If the Groq call fails after the quota is reserved, the slot is refunded — see `generate_turn` in `server_app/services/npc.py`.

## Frontend

The chat UI lives at `/latvian-a2-exam-app/npc-chat.html` (sibling to the main exam UI). It is vanilla JS, no framework dependency, and renders four UX states: empty (no NPC selected), loading (in-flight), error (server returned non-200), success (reply rendered).

## Files

- `content/npcs/*.json` — six character profiles.
- `server_app/services/npc.py` — persona load + Groq call + persistence.
- `server_app/routes/npc.py` — `do_GET` / `do_POST` dispatch hook.
- `latvian-a2-exam-app/npc-chat.html` + `npc-chat.js` — chat UI.
- `tests/server/test_npc.py` — 21 unit tests covering load, generation, persistence, isolation, schema, quota.
