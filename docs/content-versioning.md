# Exam Content Versioning & Rapid-Update Pipeline (T-037)

This document is the canonical reference for how exam content is versioned,
edited, reviewed, and published in lvcodex. It lives next to
[`docs/exam-content-schema.md`](./exam-content-schema.md) (the JSON contract)
and `docs/release-checklist.md` (the release-train cadence).

T-017 added schema validation; T-037 layers a versioned-update pipeline on
top so authors can ship small changes between release trains without an
emergency PR.

## 1. Version scheme

Every exam carries a calendar-versioned semantic version:

```
YYYY.MM.N
```

* `YYYY` — four-digit year (e.g. `2026`).
* `MM`   — zero-padded month, `01`–`12` (e.g. `05`).
* `N`    — monotonically increasing integer within that month, starting at `0`.

Examples:

| Version      | Meaning                                                       |
|--------------|----------------------------------------------------------------|
| `2026.05.0`  | First May-2026 revision of an exam.                            |
| `2026.05.1`  | Second May-2026 revision (typo fix, audio re-record, etc.).    |
| `2026.06.0`  | First June-2026 revision (e.g. new gap-fill text).             |
| `1.0.0`      | **Grandfathered** — exams that pre-date T-037 (no DB row yet). |

The version regex is enforced both in the JSON schema
(`schemas/exam.schema.json`) and at the service layer
(`server_app/services/exam_versions.VERSION_PATTERN`). New content **MUST**
set the `version` field; existing exams without a `version` field
automatically resolve to `1.0.0` for backward compatibility.

### Why YYYY.MM.N and not SemVer?

CEFR exam content doesn't have a `major.minor.patch` distinction in the
SemVer sense — every learner-visible change is a "breaking change" relative
to the previous attempt. CalVer makes it trivial to answer "which exam was
in production last May?" at a glance and to drop drift between authors
working in parallel month-blocks.

## 2. Lifecycle (status state machine)

```
            create_draft                publish_version          archive_version
   ∅  ──────────────────►  draft  ────────────────────►  published  ──────────►  archived
                              │                              ▲
                              │     publish_version          │
                              └──────────────────────────────┘
```

* **`draft`** — visible to admins only. May be edited freely.
* **`published`** — currently-served version. Exactly one per `exam_id`.
* **`archived`** — historical record. Retained for audit and quick rollback.

Transitions:

| From       | To          | Trigger                                       |
|------------|-------------|------------------------------------------------|
| ∅          | `draft`     | `scripts/update_exam_content.py`               |
| `draft`    | `published` | `POST /api/admin/exams/<id>/publish`           |
| `draft`    | `archived`  | (admin tooling — keeps the draft as history)   |
| `archived` | `published` | re-publishing for fast rollback                |
| `published`| `archived`  | implicit when a different version is published |

Publishing automatically archives the previous published row in the same
SQLite transaction, so there is always **at most one** `published` row per
`exam_id`.

## 3. Storage

A single table tracks every revision:

```sql
CREATE TABLE exam_versions (
    id           TEXT PRIMARY KEY,
    exam_id      TEXT NOT NULL,
    version      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft',
    payload      TEXT NOT NULL DEFAULT '{}',   -- JSON exam manifest
    published_at TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(exam_id, version)
);

CREATE INDEX idx_exam_versions_exam_status
    ON exam_versions(exam_id, status);
```

The table is created during `init_auth_store()` (the same bootstrap path
used by every other lvcodex SQLite table). The PG translation under T-021
is identical modulo:

* `TIMESTAMP WITH TIME ZONE` for `published_at`/`created_at`/`updated_at`,
* `JSONB` for `payload`,
* `CHECK (status IN ('draft', 'published', 'archived'))` constraint.

## 4. Rapid-update flow

The canonical end-to-end pipeline:

```
   1. Edit markdown                           (codex/A2_Mock_Exam_NN.md)
                │
                ▼
   2. python3 scripts/update_exam_content.py \
          --exam-id NN --version 2026.MM.N \
          --markdown codex/A2_Mock_Exam_NN.md
                │
                ▼  validate against schema + cross-field invariants
                ▼  insert as draft into exam_versions
                ▼  print next-step curl
                │
                ▼
   3. Admin previews draft in admin console
                │
                ▼
   4. curl -X POST /api/admin/exams/NN/publish -d '{"version": "2026.MM.N"}'
                │
                ▼  archive previous published row
                ▼  stamp published_at
                │
                ▼
   5. Learner hits  GET /api/exams/NN/content
                ▼  sees the new content + X-Exam-Version: 2026.MM.N
```

### Dry-run

CI uses `--dry-run` to fail a PR whose manifest does not satisfy the schema:

```bash
python3 scripts/update_exam_content.py \
    --exam-id 01 \
    --version 2026.05.1 \
    --markdown codex/A2_Mock_Exam_01.md \
    --dry-run
```

The dry-run mode performs schema validation and version-format checks but
does NOT touch the database. It is wired into `ci-pr.yml` so every PR that
touches `codex/*.md` is gated.

## 5. API surface

| Method | Path                                  | Auth  | Description                                              |
|--------|----------------------------------------|-------|----------------------------------------------------------|
| GET    | `/api/exams/<id>/content`              | open  | Markdown body of the currently-published version. Adds an `X-Exam-Version` response header. |
| POST   | `/api/admin/exams/<id>/publish`        | admin | Flip the named draft to `published`; archive previous published. Body: `{"version": "YYYY.MM.N"}`. |
| GET    | `/api/admin/exams/<id>/versions`       | admin | List every row (draft + published + archived) for an exam. |

Errors:

* `400 invalid_exam_version` — version is not `YYYY.MM.N`.
* `400 exam_version_transition_invalid` — re-drafting a published row.
* `404 exam_version_not_found` — the (exam_id, version) pair is unknown.
* `401 unauthenticated` — missing session cookie.
* `403 forbidden` — non-admin caller on an admin route.

## 6. Backward compatibility

* The `version` field is **optional** in the JSON schema. Existing exams
  ship today without it and they continue to work — they are pinned at the
  grandfathered baseline `1.0.0`.
* The static catalog (`built_in_exam_catalog()`) is untouched. The
  `exam_versions` table is additive; dropping it returns the system to its
  pre-T-037 behaviour with zero data loss.
* `T-017`'s `validate_exam_content.py` still passes for legacy manifests:
  it treats a missing `version` as OK and rejects only **malformed**
  versions. New manifests must opt in by setting the field.

## 7. Rollback

To revert a bad publish:

```bash
# 1. List versions to find the previous good one
curl -s http://localhost:4173/api/admin/exams/NN/versions | jq '.versions[].version'

# 2. Re-publish the previous version (no new version number needed)
curl -X POST http://localhost:4173/api/admin/exams/NN/publish \
     -H 'Content-Type: application/json' \
     -d '{"version": "2026.04.0"}'
```

`publish_version` accepts an `archived` row as input, so this is the
rapid-rollback path. The just-bad version moves to `archived`; the previous
good one becomes `published` again.

## 8. Testing

Coverage lives in `tests/server/test_exam_versions.py`. The suite asserts:

1. The schema accepts well-formed `version` strings and rejects malformed
   ones.
2. The service rejects bad version strings at write time.
3. `publish_version` archives the previously-published row in the same
   transaction (exactly one `published` row per `exam_id`).
4. Learners only see the currently-published version via
   `/api/exams/<id>/content`.
5. Admins (and only admins) see drafts via `/api/admin/exams/<id>/versions`.
6. `scripts/update_exam_content.py` --dry-run rejects an invalid manifest.

CI runs the suite under `npm run test:unit`.
