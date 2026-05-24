# Exam Content Schema (T-017)

This document describes the JSON schema that governs every exam manifest
shipped by the Latvian A2 Exam Simulator. The schema is published at
[`schemas/exam.schema.json`](../schemas/exam.schema.json) (JSON Schema
Draft 2020-12) and is enforced in CI by
[`scripts/validate_exam_content.py`](../scripts/validate_exam_content.py)
plus [`.github/workflows/ci-content.yml`](../.github/workflows/ci-content.yml).

The goal is to prevent broken or incomplete exam revisions from reaching
production — closing the **roadmap2026.md P1** item "stabilize exam-bank
import and content validation".

## Source of truth

Exam content currently lives in two places:

1. **Markdown source files** — `codex/A2_Mock_Exam_*.md`. These are the
   authoring format. They are parsed at runtime by
   `exam_bank.import_exam_markdown()`, which produces a JSON-compatible
   Python dict (the "exam manifest").
2. **Forthcoming JSON manifests** — `*.exam.json`. The validator is also
   wired to discover any file matching that pattern anywhere in the repo,
   so once exams are exported to JSON for storage (T-037 content
   versioning) the same gate applies without code changes.

The validator imports `exam_bank` for Markdown sources and reads JSON
files directly for the second case. Both paths produce the same manifest
shape, which is exactly what the schema describes.

## Top-level manifest shape

| Field             | Type             | Required | Notes                                                              |
|-------------------|------------------|----------|--------------------------------------------------------------------|
| `schema_version`  | string           | yes      | Currently `"1.0"`. Pattern `^\d+\.\d+$`.                           |
| `exam_id`         | string           | yes      | Stable identifier (e.g. `"01"`).                                   |
| `slug`            | string           | no       | URL-safe form of `exam_id`.                                        |
| `title`           | string           | yes      | Human title.                                                       |
| `level`           | enum             | yes      | One of `A2`, `B1`, `B2` (only `A2` ships today).                   |
| `language`        | string           | yes      | ISO 639-1, e.g. `"lv"`.                                            |
| `status`          | enum             | yes      | `draft` / `review` / `published` / `archived`.                     |
| `content_version` | integer ≥ 1      | yes      |                                                                    |
| `is_immutable`    | boolean          | no       | True once `status ∈ {published, archived}`.                        |
| `source`          | object           | no       | Provenance: `markdown_path`, `attachment_root`.                    |
| `workflow`        | object           | no       | Status metadata mirror of `WORKFLOW_STATUSES`.                     |
| `scoring`         | object           | yes      | See below.                                                         |
| `assets`          | object           | no       | `audio`, `images` arrays.                                          |
| `sections`        | array (length 4) | yes      | One section per CEFR skill.                                        |
| `answer_key`      | object           | no       | Parsed answer key block.                                           |
| `references`      | object           | no       | Transcripts, model answers, teacher notes.                         |
| `validation`      | object           | no       | Self-validation report from `import_and_validate`.                 |

## Scoring contract — the 9/15 rule

`scoring` is the heart of the A2 exam contract:

```json
{
  "total_points": 60,
  "skill_points": {
    "listening": 15,
    "reading":   15,
    "writing":   15,
    "speaking":  15
  },
  "minimum_per_skill": 9,
  "task_point_allocation": {
    "listening": {"task1": 6, "task2": 4, "task3": 5},
    "reading":   {"task1": 4, "task2": 6, "task3": 5},
    "writing":   {"task1": 4, "task2": 5, "task3": 6},
    "speaking":  {"task1": 10, "task2": 3, "task3": 2}
  }
}
```

The schema enforces:

- `total_points` is **exactly 60**.
- Every `skill_points.*` value is **exactly 15**.
- `minimum_per_skill` is **exactly 9** (the official A2 9/15 rule).
- Each `sections[i].points_max` is **exactly 15**.

The validator additionally enforces a cross-field invariant that the schema
cannot express cleanly: **the sum of `points_max` across the tasks of one
section must equal 15**. A skill that ships 14 or 16 points of tasks is a
T-017 failure.

## Section shape

Each of the four sections contains:

- `skill` — one of `listening`, `reading`, `writing`, `speaking`.
- `title` — Latvian title, e.g. *Klausīšanās prasmes pārbaude*.
- `points_max` — fixed at `15`.
- `minutes` — recommended time budget.
- `tasks` — array of task objects.

## Task shape

Each task object includes:

- `task_key` — matching the regex `^task[0-9]+$`.
- `title`, `instruction`, `type` (e.g. `listening_multiple_choice`).
- `scoring_mode` — `objective` / `subjective` / `mixed`.
- `points_max` — 1–15 integer.
- `assets` and/or `audio_assets` — optional asset arrays (path required).
- `questions` — array of question objects (see below). May be empty for
  fully-subjective tasks like `writing_short_message`.
- `choices`, `requirements` — optional shape-specific arrays.

## Question shape

Each question has:

- `number` — integer ≥ 1.
- `kind` — string. Examples: `objective`, `multiple_choice`, `true_false`,
  `matching`, `gap_fill`, `reading_text_choice`, `inflection`,
  `subjective_sentence`, `subjective`.
- `prompt`, `passage`, `image`, `lemma` — optional, kind-dependent.
- `options` — array of `{label, text}` for selection-style kinds.
- `correct_answer` — scalar (back-compat field).
- `correct_answers` — array. **Required and non-empty** when `kind` is in
  the objective set (`objective`, `multiple_choice`, `true_false`,
  `matching`, `gap_fill`, `reading_text_choice`, `inflection`).

This last constraint is enforced by an `allOf` / `if` / `then` block in the
schema so that an objective question without an answer key fails CI.

## Validator behavior

The validator entry point is:

```bash
python3 scripts/validate_exam_content.py [--strict] [--list]
                                         [--json path ...]
                                         [--markdown path ...]
                                         [--schema schemas/exam.schema.json]
```

It auto-discovers:

- All `*.exam.json` files under the repo root (skipping ignored
  directories like `node_modules`, `.venv`, `test-results`, `fixtures`,
  `__pycache__`).
- All `codex/A2_Mock_Exam_*.md` exam sources.

It returns:

- Exit `0` — every exam is schema-clean **or** non-clean exams are all
  in the grandfather list and the run was not `--strict`.
- Exit `1` — at least one new violation; the PR is blocked.
- Exit `2` — runtime error.

## Known violations to fix (grandfathered)

This list freezes the **pre-existing** content state. A future task can
re-balance an exam and remove it from this list. **No new exam may ever
be added here**; new content must be authored schema-clean.

At the time T-017 lands, the grandfather list is **empty** — every
shipped exam (`A2_Mock_Exam_01.md` through `A2_Mock_Exam_11.md`)
satisfies the schema today. The list infrastructure is in place so
future regressions or imports with known quirks can be deferred rather
than blocking unrelated work, per the T-017 plan note:

> If the existing exam content has minor schema violations, mark them as
> known-issues here and have the validator log warnings (exit 0) for
> those specific exam IDs while failing for any NEW violations.

To grandfather an exam, edit
`GRANDFATHERED_EXAM_IDS` in
[`scripts/validate_exam_content.py`](../scripts/validate_exam_content.py)
and document the deferred fix here with:

- exam id,
- list of failing rules,
- tracking issue link,
- target removal date.

## CI gate

The workflow [`.github/workflows/ci-content.yml`](../.github/workflows/ci-content.yml)
triggers on PRs that touch any of:

- `exam_bank.py`
- `schemas/exam.schema.json`
- `**/*.exam.json`
- `scripts/validate_exam_content.py`
- the workflow file itself

It installs `jsonschema` from `requirements.txt`, runs the validator, and
fails the PR on a non-zero exit. The full repo regression
(`npm run test:unit` + `npm run test:contracts`) also runs the
`tests/server/test_exam_content_validation.py` suite, so logic changes to
the validator are independently covered.
