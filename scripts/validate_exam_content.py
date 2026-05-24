#!/usr/bin/env python3
"""Validate exam content against schemas/exam.schema.json.

T-017 — Exam-bank content validation (JSON schema + CI gate).

This script is the CI gate that prevents broken exam revisions from reaching
production. It loads every exam manifest the codebase can produce and runs it
against the Draft 2020-12 JSON schema at ``schemas/exam.schema.json``.

Sources scanned (in priority order):

1. Standalone JSON manifests matching ``*.exam.json`` anywhere in the repo
   (this is the future-facing format).
2. Markdown sources under ``codex/A2_Mock_Exam_*.md``, parsed via
   :func:`exam_bank.import_exam_markdown` (today's authoring format).

Grandfathering
--------------
Pre-existing content that has minor schema violations is NOT auto-rewritten by
this script. Instead, exam IDs listed in :data:`GRANDFATHERED_EXAM_IDS` are
demoted from errors to warnings. The validator still exits 0 for those, but it
exits non-zero for any NEW violation. The goal of T-017 is to prevent future
regressions, not retroactively re-balance shipped content.

Exit codes
----------
0  All exams pass schema (warnings allowed for grandfathered IDs).
1  At least one non-grandfathered exam failed validation.
2  Unexpected runtime error (missing schema file, import error, etc.).

Usage
-----
    python3 scripts/validate_exam_content.py             # validate everything
    python3 scripts/validate_exam_content.py --json path1 path2 ...
    python3 scripts/validate_exam_content.py --markdown codex/A2_Mock_Exam_01.md
    python3 scripts/validate_exam_content.py --strict   # fail on warnings too
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_PATH = ROOT / "schemas" / "exam.schema.json"

# Exam IDs whose pre-existing schema violations are tolerated. Add an ID here
# only with a tracking issue/comment explaining the deferred fix. Brand-new
# exams must NOT be added here — they should be authored schema-clean.
GRANDFATHERED_EXAM_IDS: set[str] = set()

# T-037: legacy `version` placeholder used for exams authored before content
# versioning landed. The schema validator treats missing `version` as a
# grandfathered case (warning, not error) and the runtime services serve this
# constant as the "current published version" for those exams.
GRANDFATHERED_VERSION = "1.0.0"

# Calendar-versioned semantic version: YYYY.MM.N (matches schemas/exam.schema.json).
import re as _re

VERSION_PATTERN = _re.compile(r"^[0-9]{4}\.(0[1-9]|1[0-2])\.[0-9]+$")


def is_valid_version(value: str | None) -> bool:
    """Return True if ``value`` is a well-formed T-037 exam version string.

    The grandfathered legacy version ``1.0.0`` is intentionally NOT considered
    valid by this helper — callers that need to accept it must do so explicitly.
    """

    if not value or not isinstance(value, str):
        return False
    return bool(VERSION_PATTERN.match(value))


@dataclass(frozen=True)
class ExamSource:
    """A single exam manifest source: either a JSON file or a Markdown file."""

    label: str
    kind: str  # "json" | "markdown"
    path: Path


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    def ok(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Schema not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Schema is not valid JSON: {exc}") from exc


def build_validator(schema: dict[str, Any]):
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - defensive guard
        raise SystemExit(
            "jsonschema is required. Install with: pip install 'jsonschema>=4.0.0'"
        )

    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    return validator_cls(schema)


# ---------------------------------------------------------------------------
# Manifest discovery & loading
# ---------------------------------------------------------------------------


def discover_sources(
    json_paths: Iterable[Path] | None = None,
    markdown_paths: Iterable[Path] | None = None,
) -> list[ExamSource]:
    """Return the list of exam sources to validate.

    If both ``json_paths`` and ``markdown_paths`` are ``None`` we auto-discover
    everything the repo currently ships.
    """

    sources: list[ExamSource] = []

    if json_paths is None and markdown_paths is None:
        # Auto-discovery mode.
        for p in sorted(ROOT.rglob("*.exam.json")):
            if _is_ignored(p):
                continue
            sources.append(ExamSource(label=p.relative_to(ROOT).as_posix(), kind="json", path=p))
        for p in sorted((ROOT / "codex").glob("A2_Mock_Exam_*.md")):
            sources.append(ExamSource(label=p.relative_to(ROOT).as_posix(), kind="markdown", path=p))
        return sources

    for p in json_paths or []:
        sources.append(ExamSource(label=str(p), kind="json", path=Path(p)))
    for p in markdown_paths or []:
        sources.append(ExamSource(label=str(p), kind="markdown", path=Path(p)))
    return sources


def _is_ignored(path: Path) -> bool:
    """Skip ephemeral, vendored, or fixture directories."""

    parts = set(path.parts)
    ignored_dirs = {
        "node_modules",
        ".venv",
        "venv",
        ".git",
        "test-results",
        "fixtures",
        "__pycache__",
    }
    return bool(parts & ignored_dirs)


def load_manifest(source: ExamSource) -> dict[str, Any]:
    if source.kind == "json":
        return json.loads(source.path.read_text(encoding="utf-8"))
    if source.kind == "markdown":
        # Import lazily so the script can still run --list without a working
        # exam_bank (e.g. early CI environments).
        from exam_bank import import_exam_markdown

        return import_exam_markdown(source.path)
    raise ValueError(f"Unknown source kind: {source.kind}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _format_error(error: Any) -> str:
    path = "/" + "/".join(str(p) for p in error.absolute_path) if error.absolute_path else "/"
    return f"{path}: {error.message}"


def validate_source(source: ExamSource, validator: Any) -> tuple[list[str], str | None]:
    """Validate one source.

    Returns ``(messages, exam_id)`` where ``messages`` is the formatted list of
    schema-error strings (empty if valid) and ``exam_id`` is the exam_id pulled
    from the manifest (used for grandfathering lookup).
    """

    try:
        manifest = load_manifest(source)
    except Exception as exc:  # noqa: BLE001 - surface any load failure
        return ([f"failed to load: {exc}"], None)

    exam_id = str(manifest.get("exam_id") or "")
    errors = list(validator.iter_errors(manifest))
    messages = [_format_error(e) for e in errors]

    # Cross-field invariant the JSON Schema cannot express cleanly: each
    # skill's per-task points must sum to that skill's allotted 15.
    for section in manifest.get("sections") or []:
        skill = section.get("skill", "?")
        tasks = section.get("tasks") or []
        total = sum(int(t.get("points_max") or 0) for t in tasks)
        if total != 15:
            messages.append(
                f"/sections/{skill}/tasks: per-task points sum to {total}, expected 15 (9/15 rule)"
            )

    # T-037: enforce semantic version format when present. Missing `version`
    # is allowed (grandfathered to 1.0.0); malformed `version` is rejected.
    raw_version = manifest.get("version")
    if raw_version is not None and not is_valid_version(str(raw_version)):
        messages.append(
            f"/version: '{raw_version}' is not a valid YYYY.MM.N exam version (T-037)"
        )

    return (messages, exam_id or None)


def run(
    sources: list[ExamSource],
    schema: dict[str, Any],
    *,
    strict: bool = False,
) -> ValidationReport:
    validator = build_validator(schema)
    report = ValidationReport()

    for source in sources:
        report.checked += 1
        messages, exam_id = validate_source(source, validator)
        if not messages:
            continue
        grandfathered = exam_id in GRANDFATHERED_EXAM_IDS
        target = report.warnings if grandfathered and not strict else report.errors
        for msg in messages:
            prefix = "WARN" if target is report.warnings else "FAIL"
            target.append(f"[{prefix}] {source.label} (exam_id={exam_id or '?'}): {msg}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate exam content against the JSON schema.")
    parser.add_argument(
        "--json",
        nargs="*",
        type=Path,
        help="Explicit JSON exam manifest path(s). Default: auto-discover *.exam.json under repo.",
    )
    parser.add_argument(
        "--markdown",
        nargs="*",
        type=Path,
        help="Explicit Markdown exam path(s) to import via exam_bank. Default: auto-discover codex/A2_Mock_Exam_*.md.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat grandfathered exam warnings as errors (used for new-content gates).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List discovered exam sources and exit without validating.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help=f"Path to JSON schema (default: {SCHEMA_PATH.relative_to(ROOT)}).",
    )
    args = parser.parse_args(argv)

    json_paths = args.json if args.json is not None else None
    md_paths = args.markdown if args.markdown is not None else None
    sources = discover_sources(json_paths=json_paths, markdown_paths=md_paths)

    if args.list:
        for source in sources:
            print(f"{source.kind}\t{source.label}")
        return 0

    if not sources:
        print("validate_exam_content: no exam sources discovered", file=sys.stderr)
        return 0  # nothing to validate is not a failure

    schema = load_schema(args.schema)
    report = run(sources, schema, strict=args.strict)

    for msg in report.warnings:
        print(msg)
    for msg in report.errors:
        print(msg, file=sys.stderr)

    summary = (
        f"validate_exam_content: checked={report.checked} "
        f"errors={len(report.errors)} warnings={len(report.warnings)}"
    )
    print(summary, file=sys.stderr if report.errors else sys.stdout)
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
