#!/usr/bin/env python3
"""Rapid-update pipeline driver for exam content (T-037).

Workflow
--------
1. Author edits a markdown file under ``codex/``.
2. They run::

       python3 scripts/update_exam_content.py \
           --exam-id 01 \
           --version 2026.05.1 \
           --markdown codex/A2_Mock_Exam_01.md

3. This script:

   * imports the markdown into a manifest via ``exam_bank.import_exam_markdown``,
   * stamps the requested ``--version`` into the manifest (T-037 semver),
   * validates the manifest against ``schemas/exam.schema.json`` using the
     shared :mod:`validate_exam_content` helpers (zero schema drift),
   * inserts the manifest as a ``draft`` row in the ``exam_versions`` table,
   * prints the exact next-step ``curl`` admins need to publish the draft.

4. Admin runs the printed POST to ``/api/admin/exams/<exam_id>/publish`` to
   make the version live for learners.

Exit codes
----------
0   draft persisted, next steps printed.
1   validation failed — no DB write occurred.
2   unexpected error (missing file, DB unreachable, etc.).

Design notes
------------
The script intentionally does not "publish" the draft itself. The
draft-then-publish split is the entire point of T-037: it gives a human
reviewer a window to preview before learners see the change. ``--dry-run``
runs the validation-and-version-format checks without touching the DB,
which is what CI uses to fail a PR that ships an invalid manifest.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_validator_module():
    """Import scripts/validate_exam_content.py as a module."""

    if "validate_exam_content" in sys.modules:
        return sys.modules["validate_exam_content"]
    spec = importlib.util.spec_from_file_location(
        "validate_exam_content", ROOT / "scripts" / "validate_exam_content.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_exam_content"] = module
    spec.loader.exec_module(module)
    return module


def _print_next_steps(exam_id: str, version: str) -> None:
    print()
    print("Draft saved. Next steps:")
    print(f"  1. Preview the draft locally (open the admin console for exam {exam_id}).")
    print("  2. When happy, publish:")
    print(
        "       curl -X POST http://localhost:4173/api/admin/exams/"
        f"{exam_id}/publish \\"
    )
    print('         -H "Content-Type: application/json" \\')
    print(f'         -d \'{{"version": "{version}"}}\'')
    print(
        "  3. Verify with: "
        f"curl -i http://localhost:4173/api/exams/{exam_id}/content | head -5"
    )
    print("     (expect 'X-Exam-Version: " + version + "')")
    print()


def _stamp_version(manifest: dict[str, Any], version: str) -> dict[str, Any]:
    """Return a copy of ``manifest`` with the T-037 version field set."""

    out = dict(manifest)
    out["version"] = version
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="T-037 — validate a markdown exam and insert it as a draft version."
    )
    parser.add_argument(
        "--exam-id",
        required=True,
        help="The exam_id the draft applies to (e.g. '01').",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Semantic version YYYY.MM.N (e.g. 2026.05.1).",
    )
    parser.add_argument(
        "--markdown",
        required=True,
        type=Path,
        help="Path to the markdown source file under codex/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only; do not touch the DB. CI uses this in PR gating.",
    )
    args = parser.parse_args(argv)

    md_path = args.markdown.resolve()
    if not md_path.is_file():
        print(f"Markdown file not found: {md_path}", file=sys.stderr)
        return 2

    validator_module = _load_validator_module()

    # Import exam_bank lazily so validation-only mode without the full
    # server install (e.g. early CI) keeps working.
    try:
        from exam_bank import import_exam_markdown
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to import exam_bank.import_exam_markdown: {exc}", file=sys.stderr)
        return 2

    try:
        manifest = import_exam_markdown(md_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to parse markdown: {exc}", file=sys.stderr)
        return 2

    manifest = _stamp_version(manifest, args.version)

    # Reuse the validator: same schema, same cross-field invariants, same
    # version-format rule. This guarantees the script and the CI gate stay
    # in lockstep.
    if not validator_module.is_valid_version(args.version):
        print(
            f"--version '{args.version}' is not a valid YYYY.MM.N exam version (T-037)",
            file=sys.stderr,
        )
        return 1

    schema = validator_module.load_schema()
    validator = validator_module.build_validator(schema)
    errors = [validator_module._format_error(e) for e in validator.iter_errors(manifest)]

    # Cross-field invariant: per-task points must sum to 15 per skill.
    for section in manifest.get("sections") or []:
        skill = section.get("skill", "?")
        tasks = section.get("tasks") or []
        total = sum(int(t.get("points_max") or 0) for t in tasks)
        if total != 15:
            errors.append(
                f"/sections/{skill}/tasks: per-task points sum to {total}, expected 15 (9/15 rule)"
            )

    if errors:
        print("Validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        f"Validation OK — exam_id={args.exam_id} version={args.version} "
        f"sections={len(manifest.get('sections') or [])}"
    )

    if args.dry_run:
        print("(--dry-run: skipping DB write)")
        return 0

    # Persist the draft. Imported lazily so --dry-run keeps working
    # without a live SQLite at the AUTH_DB_PATH location.
    try:
        from server_app import core as _server_core
        from server_app.services import exam_versions
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to import server_app: {exc}", file=sys.stderr)
        return 2

    try:
        with _server_core.db_connection() as conn:
            row = exam_versions.create_draft(
                conn,
                exam_id=str(args.exam_id),
                version=str(args.version),
                payload=manifest,
            )
    except exam_versions.ExamVersionError as exc:
        print(f"Could not insert draft: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Database error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(row, indent=2, sort_keys=True, default=str))
    _print_next_steps(str(args.exam_id), str(args.version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
