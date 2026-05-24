#!/usr/bin/env python3
"""Generate student-facing markdown for B1 mock exams (T-060).

The canonical authoring format for B1 is the JSON manifest under
``content/exams/B1/*.exam.json`` — it carries the full schema-validated
structure (sections, tasks, questions, audio asset paths, answer key,
scoring). This script projects each manifest into the lightweight
student-facing markdown that the catalog endpoint serves at
``GET /api/exams/<id>/content``.

It is intentionally one-way: edit the JSON manifest, then re-run this
script. Do not hand-edit the generated ``.md`` files — they will be
overwritten.

Usage::

    python3 scripts/build_b1_markdown.py
    python3 scripts/build_b1_markdown.py --check    # CI mode: fail if stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B1_DIR = ROOT / "content" / "exams" / "B1"


def _render_question(q: dict, idx: int) -> list[str]:
    out: list[str] = []
    prompt = q.get("prompt") or ""
    out.append(f"{idx}. {prompt}".rstrip())
    options = q.get("options") or []
    for opt in options:
        label = opt.get("label", "")
        text = opt.get("text", "")
        out.append(f"   - {label}) {text}")
    if not options and q.get("minimum_words"):
        out.append(f"   _(vismaz {q['minimum_words']} vārdu)_")
    return out


def _render_task(task: dict) -> list[str]:
    out: list[str] = []
    title = task.get("title") or task.get("task_key", "")
    out.append(f"#### {title}")
    out.append("")
    points = task.get("points_max")
    if points:
        out.append(f"_Punkti: {points}_")
        out.append("")
    instruction = (task.get("instruction") or "").strip()
    if instruction:
        out.append(instruction)
        out.append("")
    for audio in task.get("audio_assets") or []:
        path = audio.get("path", "")
        label = audio.get("label", "Audio")
        out.append(f'<audio controls preload="none">')
        out.append(f'  <source src="{path}" type="audio/mpeg">')
        out.append(f"  Your browser does not support the audio element.")
        out.append(f"</audio>")
        out.append("")
        out.append(f"[Audio failsafe link]({path}) — {label}")
        out.append("")
    prompt = (task.get("prompt") or "").strip()
    if prompt:
        out.append("> " + prompt.replace("\n", "\n> "))
        out.append("")
    questions = task.get("questions") or []
    for i, q in enumerate(questions, start=1):
        out.extend(_render_question(q, i))
    requirements = task.get("requirements") or []
    if requirements:
        out.append("")
        out.append("**Prasības:**")
        for req in requirements:
            out.append(f"- {req}")
    out.append("")
    return out


def render_manifest(manifest: dict) -> str:
    title = manifest.get("title") or "B1 Mock Exam"
    level = manifest.get("level", "B1")
    scoring = manifest.get("scoring") or {}
    min_per = scoring.get("minimum_per_skill", 12)
    total = scoring.get("total_points", 60)

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"> Auto-generated from `{Path(manifest.get('source', {}).get('markdown_path') or '').name or 'B1_Mock_Exam.exam.json'}` "
        "by scripts/build_b1_markdown.py. Do not hand-edit."
    )
    lines.append("")
    lines.append("## Student Version")
    lines.append("")
    lines.append("Klausīšanās – 15 punkti  ")
    lines.append("Lasīšana – 15 punkti  ")
    lines.append("Rakstīšana – 15 punkti  ")
    lines.append("Runāšana – 15 punkti  ")
    lines.append(f"Kopā – {total} punkti  ")
    lines.append(
        f"Lai nokārtotu: vismaz {min_per} punkti katrā prasmē "
        f"(minimum {min_per} points in each skill — {level} pass rule)"
    )
    lines.append("")
    for section in manifest.get("sections") or []:
        skill_title = section.get("title", section.get("skill", ""))
        lines.append(f"### {skill_title}")
        lines.append("")
        minutes = section.get("minutes")
        if minutes:
            lines.append(f"Laiks – {minutes} minūtes")
            lines.append("")
        for task in section.get("tasks") or []:
            lines.extend(_render_task(task))
    return "\n".join(lines).rstrip() + "\n"


def manifest_to_md_path(json_path: Path) -> Path:
    # B1_Mock_Exam_01.exam.json -> B1_Mock_Exam_01.md
    name = json_path.name.replace(".exam.json", ".md")
    return json_path.with_name(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the generated markdown is in sync with the JSON manifests. "
             "Exit 1 if any file would change.",
    )
    args = parser.parse_args(argv)

    json_files = sorted(B1_DIR.glob("B1_Mock_Exam_*.exam.json"))
    if not json_files:
        print(f"No B1 manifests found under {B1_DIR}", file=sys.stderr)
        return 0

    stale: list[Path] = []
    for json_path in json_files:
        manifest = json.loads(json_path.read_text(encoding="utf-8"))
        md_path = manifest_to_md_path(json_path)
        new_content = render_manifest(manifest)
        current = md_path.read_text(encoding="utf-8") if md_path.exists() else None
        if current == new_content:
            continue
        if args.check:
            stale.append(md_path)
        else:
            md_path.write_text(new_content, encoding="utf-8")
            print(f"wrote {md_path.relative_to(ROOT)}")

    if args.check and stale:
        print("stale markdown files (run scripts/build_b1_markdown.py to refresh):",
              file=sys.stderr)
        for p in stale:
            print(f"  {p.relative_to(ROOT)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
