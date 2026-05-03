#!/usr/bin/env python3
"""Import Latvian A2 exam Markdown into structured JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from exam_bank import import_and_validate, to_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exam", nargs="+", help="Markdown exam file(s) to import.")
    parser.add_argument("--status", default="draft", help="Workflow status to assign.")
    parser.add_argument("--content-version", type=int, default=1, help="Content version to record.")
    parser.add_argument("--output-dir", help="Write JSON files to this directory instead of stdout.")
    parser.add_argument("--validate", action="store_true", help="Validate the imported manifest before writing.")
    parser.add_argument("--fail-on-warning", action="store_true", help="Reserved for future use.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for exam in args.exam:
        manifest, issues = import_and_validate(
            ROOT / exam if not Path(exam).is_absolute() else Path(exam),
            status=args.status,
            content_version=args.content_version,
            root_dir=ROOT,
        )
        if args.validate and issues:
            exit_code = 1
            print(f"{exam}: validation failed with {len(issues)} issue(s)", file=sys.stderr)
            for issue in issues:
                print(f"- {issue.path}: {issue.message} [{issue.code}]", file=sys.stderr)
        if output_dir is None:
            print(to_json(manifest))
        else:
            target = output_dir / f"{Path(exam).stem}.json"
            target.write_text(to_json(manifest) + "\n", encoding="utf-8")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
