"""Structured Latvian A2 exam importer and validator.

This module converts the existing Markdown mock exam format into a typed JSON
manifest that is suitable for governance, validation, and downstream storage.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
WORKFLOW_STATUSES = ("draft", "review", "published", "archived")
SKILL_ORDER = ("listening", "reading", "writing", "speaking")
SKILL_TITLES = {
    "listening": "Klausīšanās prasmes pārbaude",
    "reading": "Lasītprasmes pārbaude",
    "writing": "Rakstītprasmes pārbaude",
    "speaking": "Runātprasmes pārbaude",
}
SKILL_TOTAL_POINTS = {
    "listening": 15,
    "reading": 15,
    "writing": 15,
    "speaking": 15,
}
TASK_POINT_ALLOCATION = {
    "listening": {"task1": 6, "task2": 4, "task3": 5},
    "reading": {"task1": 4, "task2": 6, "task3": 5},
    "writing": {"task1": 4, "task2": 5, "task3": 6},
    "speaking": {"task1": 10, "task2": 3, "task3": 2},
}


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    path: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "severity": self.severity,
        }


class ExamValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        message = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        super().__init__(message or "Exam validation failed.")


def import_exam_markdown(
    markdown_path: str | Path,
    *,
    status: str = "draft",
    content_version: int = 1,
) -> dict[str, Any]:
    """Import an exam Markdown file into a structured JSON manifest."""

    path = Path(markdown_path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = extract_title(lines) or path.stem.replace("_", " ")
    exam_id = extract_exam_id(path)
    sections = parse_sections(lines)
    answer_key = parse_answer_key(lines)
    apply_answer_key(sections, answer_key)
    references = parse_reference_sections(lines)
    assets = extract_assets(lines, path)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "exam_id": exam_id,
        "slug": slugify_exam_id(exam_id),
        "title": title,
        "level": "A2",
        "language": "lv",
        "status": validate_status(status),
        "content_version": int(content_version),
        "is_immutable": status in {"published", "archived"},
        "source": {
            "markdown_path": path.as_posix(),
            "attachment_root": f"codex/Attachments/{path.stem}",
        },
        "workflow": {
            "status_values": list(WORKFLOW_STATUSES),
            "immutable_statuses": ["published", "archived"],
            "current_status": validate_status(status),
        },
        "scoring": {
            "total_points": 60,
            "skill_points": SKILL_TOTAL_POINTS,
            "minimum_per_skill": 9,
            "task_point_allocation": TASK_POINT_ALLOCATION,
            "pass_rule": {
                "minimum_per_skill": 9,
                "total_points": 60,
            },
        },
        "assets": assets,
        "sections": sections,
        "answer_key": answer_key,
        "references": references,
    }
    return manifest


def validate_exam_manifest(manifest: dict[str, Any], *, root_dir: str | Path | None = None) -> list[ValidationIssue]:
    """Validate a manifest and return a list of issues."""

    root = Path(root_dir) if root_dir is not None else Path.cwd()
    issues: list[ValidationIssue] = []

    if manifest.get("schema_version") != SCHEMA_VERSION:
        issues.append(issue("schema-version", "Unexpected schema version.", "schema_version"))

    status = manifest.get("status")
    if status not in WORKFLOW_STATUSES:
        issues.append(issue("invalid-status", "Workflow status is not recognized.", "status"))

    content_version = manifest.get("content_version")
    if not isinstance(content_version, int) or content_version < 1:
        issues.append(issue("invalid-version", "Content version must be a positive integer.", "content_version"))

    if status == "published" and manifest.get("is_immutable") is not True:
        issues.append(
            issue(
                "published-immutable",
                "Published exams must be marked immutable.",
                "is_immutable",
            )
        )

    scoring = manifest.get("scoring") or {}
    if scoring.get("total_points") != 60:
        issues.append(issue("total-points", "Total points must equal 60.", "scoring.total_points"))

    skill_points = scoring.get("skill_points") or {}
    for skill in SKILL_ORDER:
        if skill_points.get(skill) != 15:
            issues.append(
                issue(
                    "skill-points",
                    f"{skill} must be worth 15 points.",
                    f"scoring.skill_points.{skill}",
                )
            )

    sections = manifest.get("sections") or []
    if len(sections) != 4:
        issues.append(issue("section-count", "Expected four skill sections.", "sections"))

    for section in sections:
        skill = section.get("skill")
        section_path = f"sections.{skill or 'unknown'}"
        if skill not in SKILL_ORDER:
            issues.append(issue("invalid-skill", "Section skill is not recognized.", section_path))
            continue

        if section.get("title") != SKILL_TITLES[skill]:
            issues.append(issue("section-title", "Section title does not match the skill.", f"{section_path}.title"))

        if section.get("points_max") != 15:
            issues.append(issue("section-points", "Each section must total 15 points.", f"{section_path}.points_max"))

        tasks = section.get("tasks") or []
        expected_tasks = TASK_POINT_ALLOCATION.get(skill, {})
        if len(tasks) != 3:
            issues.append(issue("task-count", "Each section must contain three tasks.", f"{section_path}.tasks"))

        section_points = 0
        for task in tasks:
            task_key = task.get("task_key")
            task_path = f"{section_path}.tasks.{task_key or 'unknown'}"
            task_points = task.get("points_max")
            if task_key not in expected_tasks:
                issues.append(issue("invalid-task", "Unexpected task key.", task_path))
                continue

            if task_points != expected_tasks[task_key]:
                issues.append(
                    issue(
                        "task-points",
                        f"{task_key} must be worth {expected_tasks[task_key]} points.",
                        f"{task_path}.points_max",
                    )
                )
            if task.get("scoring_mode") not in {"objective", "subjective", "mixed"}:
                issues.append(issue("scoring-mode", "Missing scoring metadata.", f"{task_path}.scoring_mode"))

            section_points += int(task_points or 0)

            if task.get("assets"):
                for asset_index, asset in enumerate(task.get("assets") or []):
                    asset_path = f"{task_path}.assets.{asset_index}"
                    if not asset.get("path"):
                        issues.append(issue("asset-path", "Asset path is missing.", asset_path))
                        continue
                    if not asset_exists(asset["path"], root):
                        issues.append(
                            issue(
                                "broken-asset",
                                f"Missing asset file: {asset['path']}",
                                asset_path,
                            )
                        )

            for question in task.get("questions") or []:
                question_path = f"{task_path}.questions.{question.get('number', 'unknown')}"
                options = question.get("options") or []
                if options:
                    normalized = [normalize_text(option.get("text", "")) for option in options]
                    if len(set(normalized)) != len(normalized):
                        issues.append(
                            issue(
                                "duplicate-options",
                                "Question options contain duplicates.",
                                f"{question_path}.options",
                            )
                        )
                answers = question.get("correct_answers") or []
                if question.get("kind") in {"objective", "multiple_choice", "true_false", "matching", "gap_fill"} and not answers:
                    issues.append(
                        issue(
                            "missing-answer-key",
                            "Objective question is missing a correct answer.",
                            f"{question_path}.correct_answers",
                        )
                    )

        if section_points != 15:
            issues.append(
                issue(
                    "section-total",
                    "Section task points do not sum to 15.",
                    f"{section_path}.tasks",
                )
            )

    return issues


def import_and_validate(
    markdown_path: str | Path,
    *,
    status: str = "draft",
    content_version: int = 1,
    root_dir: str | Path | None = None,
) -> tuple[dict[str, Any], list[ValidationIssue]]:
    manifest = import_exam_markdown(markdown_path, status=status, content_version=content_version)
    issues = validate_exam_manifest(manifest, root_dir=root_dir)
    manifest["validation"] = {
        "valid": not issues,
        "issues": [issue.as_dict() for issue in issues],
    }
    return manifest, issues


def parse_sections(lines: list[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    end_markers = {
        "listening": ["### Lasītprasmes pārbaude", "## Answer Key"],
        "reading": ["### Rakstītprasmes pārbaude", "## Answer Key"],
        "writing": ["### Runātprasmes pārbaude", "## Answer Key"],
        "speaking": ["## Answer Key"],
    }
    for skill in SKILL_ORDER:
        title = SKILL_TITLES[skill]
        section_lines = section_between(
            lines,
            f"### {title}",
            end_markers[skill],
        )
        if not section_lines:
            continue
        tasks = parse_tasks(skill, section_lines)
        sections.append(
            {
                "skill": skill,
                "title": title,
                "points_max": 15,
                "minutes": skill_minutes(skill),
                "tasks": tasks,
            }
        )
    return sections


def parse_tasks(skill: str, section_lines: list[str]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    task_blocks = split_task_blocks(section_lines)
    for task_key, block in task_blocks:
        parser = TASK_PARSERS.get((skill, task_key), parse_generic_task)
        tasks.append(parser(skill, task_key, block))
    return tasks


def parse_generic_task(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "scoring_mode": "mixed",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": strip_task_heading(block),
        "raw_markdown": "\n".join(block).strip(),
        "questions": [],
        "assets": extract_task_assets(block),
    }


def apply_answer_key(sections: list[dict[str, Any]], answer_key: dict[str, Any]) -> None:
    for section in sections:
        skill = section.get("skill")
        section_answers = answer_key.get(skill, {})
        for task in section.get("tasks", []):
            task_key = task.get("task_key")
            expected = section_answers.get(task_key, [])
            if not expected:
                continue
            questions = task.get("questions") or []
            for index, question in enumerate(questions):
                if index >= len(expected):
                    break
                question["correct_answers"] = [expected[index]]
                if question.get("kind") in {"matching"}:
                    question["correct_answer"] = expected[index]
                elif question.get("kind") in {"true_false"}:
                    question["correct_answer"] = expected[index]
                elif question.get("kind") in {"multiple_choice", "objective", "gap_fill", "reading_text_choice", "inflection"}:
                    question["correct_answer"] = expected[index]


def parse_listening_task1(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    audio = extract_audio_assets(block)
    questions = parse_mc_questions(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "listening_multiple_choice",
        "scoring_mode": "objective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.",)),
        "audio_assets": audio,
        "assets": audio,
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_listening_task2(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    audio = extract_audio_assets(block)
    questions = parse_numbered_statements(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "listening_true_false",
        "scoring_mode": "objective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.",)),
        "audio_assets": audio,
        "assets": audio,
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_listening_task3(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    audio = extract_audio_assets(block)
    questions = parse_gap_fill_questions(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "listening_gap_fill",
        "scoring_mode": "objective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.", "Atbilžu varianti")),
        "audio_assets": audio,
        "assets": audio,
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_reading_task1(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    questions = parse_text_choice_questions(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "reading_text_choice",
        "scoring_mode": "objective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("**Teksts 1**",)),
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_reading_task2(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    questions, choices = parse_matching_task(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "reading_matching",
        "scoring_mode": "objective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("**Situācijas**",)),
        "questions": questions,
        "choices": choices,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_reading_task3(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    questions = parse_numbered_choices(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "reading_gap_choice",
        "scoring_mode": "objective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.",)),
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_writing_task1(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    images = extract_image_assets(block)
    descriptions = extract_numbered_texts(block)
    questions = []
    for index, description in enumerate(descriptions):
        image = images[index] if index < len(images) else None
        questions.append(
            {
                "number": index + 1,
                "prompt": description,
                "image": image,
                "required_sentence_count": 1,
                "minimum_words": 5,
                "kind": "subjective_sentence",
                "correct_answers": [],
            }
        )
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "writing_picture_sentence",
        "scoring_mode": "subjective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.",)),
        "assets": images,
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_writing_task2(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    questions = parse_bracket_inflection_items(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "writing_inflection",
        "scoring_mode": "objective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.",)),
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_writing_task3(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "writing_short_message",
        "scoring_mode": "subjective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.",)),
        "requirements": extract_numbered_texts(block),
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_speaking_task1(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    questions = extract_numbered_texts(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "speaking_interview",
        "scoring_mode": "subjective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.",)),
        "questions": [{"number": index + 1, "prompt": text, "kind": "full_sentence"} for index, text in enumerate(questions)],
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_speaking_task2(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    images = extract_image_assets(block)
    prompts = parse_speaking_prompts(block)
    questions = []
    for index, prompt in enumerate(prompts):
        questions.append(
            {
                "number": index + 1,
                "prompt": prompt,
                "image": images[index] if index < len(images) else None,
                "kind": "picture_prompt",
            }
        )
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "speaking_picture_prompt",
        "scoring_mode": "subjective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("![", "**Jautājums jums:**")),
        "assets": images,
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


def parse_speaking_task3(skill: str, task_key: str, block: list[str]) -> dict[str, Any]:
    questions = parse_notices_for_questions(block)
    return {
        "task_key": task_key,
        "title": task_title(task_key),
        "type": "speaking_question_formulation",
        "scoring_mode": "subjective",
        "points_max": TASK_POINT_ALLOCATION[skill][task_key],
        "instruction": extract_instruction(block, stop_markers=("1.",)),
        "questions": questions,
        "raw_markdown": "\n".join(block).strip(),
    }


TASK_PARSERS = {
    ("listening", "task1"): parse_listening_task1,
    ("listening", "task2"): parse_listening_task2,
    ("listening", "task3"): parse_listening_task3,
    ("reading", "task1"): parse_reading_task1,
    ("reading", "task2"): parse_reading_task2,
    ("reading", "task3"): parse_reading_task3,
    ("writing", "task1"): parse_writing_task1,
    ("writing", "task2"): parse_writing_task2,
    ("writing", "task3"): parse_writing_task3,
    ("speaking", "task1"): parse_speaking_task1,
    ("speaking", "task2"): parse_speaking_task2,
    ("speaking", "task3"): parse_speaking_task3,
}


def parse_reference_sections(lines: list[str]) -> dict[str, Any]:
    references: dict[str, Any] = {}
    answer_start = find_heading_index(lines, "## Answer Key")
    if answer_start is not None:
        references["answer_key_raw"] = "\n".join(lines[answer_start:]).strip()

    listening_start = find_heading_index(lines, "## Listening Transcripts")
    if listening_start is not None:
        writing_start = find_heading_index(lines, "## Writing Model Answers")
        references["listening_transcripts"] = "\n".join(lines[listening_start:writing_start if writing_start is not None else len(lines)]).strip()

    writing_start = find_heading_index(lines, "## Writing Model Answers")
    if writing_start is not None:
        speaking_start = find_heading_index(lines, "## Speaking Teacher Notes")
        references["writing_model_answers"] = "\n".join(lines[writing_start:speaking_start if speaking_start is not None else len(lines)]).strip()

    speaking_start = find_heading_index(lines, "## Speaking Teacher Notes")
    if speaking_start is not None:
        references["speaking_teacher_notes"] = "\n".join(lines[speaking_start:]).strip()

    return references


def parse_answer_key(lines: list[str]) -> dict[str, Any]:
    answer_start = find_heading_index(lines, "## Answer Key")
    if answer_start is None:
        return {}

    parsed: dict[str, Any] = {}
    current_skill = ""
    current_skill_key = ""
    for line in lines[answer_start + 1 :]:
        if line.strip().startswith("## "):
            break
        skill_match = re.match(r"^###\s+(.+)$", line.strip())
        if skill_match:
            current_skill = skill_match.group(1).strip()
            current_skill_key = skill_from_heading(current_skill)
            if current_skill_key:
                parsed.setdefault(current_skill_key, {})
            continue

        if not current_skill_key:
            continue

        task_match = re.match(r"^\*{0,2}\s*(\d+)\.?\s*uzdevums:?\*{0,2}\s*(.*)$", line.strip().strip("*"), re.I)
        if not task_match:
            continue

        task_key = f"task{task_match.group(1)}"
        parsed[current_skill_key][task_key] = parse_answer_values(task_match.group(2))

    return parsed


def parse_answer_values(text: str) -> list[str]:
    values: list[str] = []
    for chunk in re.split(r"[;,]", text):
        cleaned = chunk.strip()
        if not cleaned:
            continue
        if "." in cleaned:
            _, answer = cleaned.split(".", 1)
            values.append(clean_answer(answer))
        else:
            values.append(clean_answer(cleaned))
    return values


def parse_mc_questions(block: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in block:
        question_match = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
        option_match = re.match(r"^\s*-\s*([a-z])\)\s*(.+)$", line, re.I)
        if question_match:
            current = {
                "number": int(question_match.group(1)),
                "prompt": clean_answer(question_match.group(2)),
                "kind": "objective",
                "options": [],
                "correct_answers": [],
            }
            questions.append(current)
            continue
        if option_match and current is not None:
            current["options"].append(
                {
                    "label": option_match.group(1).lower(),
                    "text": clean_answer(option_match.group(2)),
                }
            )
    return questions


def parse_numbered_statements(block: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for line in block:
        match = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
        if match:
            questions.append(
                {
                    "number": int(match.group(1)),
                    "prompt": clean_answer(match.group(2)),
                    "kind": "true_false",
                    "options": [{"label": "jā", "text": "Jā"}, {"label": "nē", "text": "Nē"}],
                    "correct_answers": [],
                }
            )
    return questions


def parse_gap_fill_questions(block: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for line in block:
        match = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
        if match:
            questions.append(
                {
                    "number": int(match.group(1)),
                    "prompt": clean_answer(match.group(2)),
                    "kind": "gap_fill",
                    "correct_answers": [],
                }
            )
    return questions


def parse_text_choice_questions(block: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current_text: dict[str, Any] | None = None
    current_options: list[dict[str, str]] = []
    passage_lines: list[str] = []
    mode = "passage"

    for line in block:
        text_match = re.match(r"^\*\*Teksts\s+(\d+)\*\*$", line.strip())
        option_match = re.match(r"^\s*-\s*([a-c])\)\s*(.+)$", line, re.I)
        if text_match:
            if current_text is not None:
                current_text["passage"] = clean_block(passage_lines)
                current_text["options"] = current_options
                questions.append(current_text)
            current_text = {
                "number": int(text_match.group(1)),
                "kind": "reading_text_choice",
                "passage": "",
                "options": [],
                "correct_answers": [],
            }
            current_options = []
            passage_lines = []
            mode = "passage"
            continue

        if current_text is None:
            continue

        if option_match:
            mode = "options"
            current_options.append(
                {
                    "label": option_match.group(1).lower(),
                    "text": clean_answer(option_match.group(2)),
                }
            )
            continue

        if mode == "passage":
            passage_lines.append(line)

    if current_text is not None:
        current_text["passage"] = clean_block(passage_lines)
        current_text["options"] = current_options
        questions.append(current_text)

    return questions


def parse_matching_task(block: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    situations: list[dict[str, Any]] = []
    choices: list[dict[str, Any]] = []
    mode = ""
    for line in block:
        if line.strip().startswith("**Situācijas**"):
            mode = "situations"
            continue
        if line.strip().startswith("**Sludinājumi**"):
            mode = "choices"
            continue
        if mode == "situations":
            match = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
            if match:
                situations.append({"number": int(match.group(1)), "prompt": clean_answer(match.group(2)), "kind": "matching"})
        elif mode == "choices":
            match = re.match(r"^\s*-\s*([A-L])\.\s*(.+)$", line)
            if match:
                choices.append({"label": match.group(1), "text": clean_answer(match.group(2))})
    return situations, choices


def parse_numbered_choices(block: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in block:
        match = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
        option_match = re.match(r"^\s*-\s*([a-z])\)\s*(.+)$", line, re.I)
        if match and current is None:
            current = {
                "number": int(match.group(1)),
                "prompt": clean_answer(match.group(2)),
                "kind": "multiple_choice",
                "options": [],
                "correct_answers": [],
            }
            questions.append(current)
            continue
        if current is not None and option_match:
            current["options"].append(
                {
                    "label": option_match.group(1).lower(),
                    "text": clean_answer(option_match.group(2)),
                }
            )
        elif match:
            current = {
                "number": int(match.group(1)),
                "prompt": clean_answer(match.group(2)),
                "kind": "multiple_choice",
                "options": [],
                "correct_answers": [],
            }
            questions.append(current)
    return questions


def parse_bracket_inflection_items(block: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for line in block:
        match = re.match(r"^\s*(\d+)\.\s*(.+)\(([^)]+)\)\.\s*$", line)
        if match:
            questions.append(
                {
                    "number": int(match.group(1)),
                    "prompt": clean_answer(match.group(2)),
                    "lemma": clean_answer(match.group(3)),
                    "kind": "inflection",
                    "correct_answers": [],
                }
            )
    return questions


def parse_speaking_prompts(block: list[str]) -> list[str]:
    prompts: list[str] = []
    for line in block:
        match = re.match(r"^\*\*Attēls\s+[AB]\.\*\*\s*(.+)$", line.strip())
        if match:
            prompts.append(clean_answer(match.group(1)))
    return prompts


def parse_notices_for_questions(block: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for line in block:
        match = re.match(r"^\s*(\d+)\.\s*(.+)\s*$", line)
        if match and not match.group(2).startswith("Uzdodiet"):
            questions.append(
                {
                    "number": int(match.group(1)),
                    "prompt": clean_answer(match.group(2)),
                    "kind": "question_formulation",
                    "correct_answers": [],
                }
            )
    return questions


def extract_numbered_texts(block: list[str]) -> list[str]:
    items: list[str] = []
    for line in block:
        match = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
        if match:
            items.append(clean_answer(match.group(2)))
    return items


def extract_instruction(block: list[str], *, stop_markers: tuple[str, ...]) -> str:
    body = strip_task_heading(block)
    collected: list[str] = []
    for line in body:
        if any(line.strip().startswith(marker) for marker in stop_markers):
            break
        if is_asset_line(line):
            continue
        collected.append(line)
    return clean_block(collected)


def strip_task_heading(block: list[str]) -> list[str]:
    if not block:
        return []
    return block[1:] if re.match(r"^####\s+\d+\.\s*uzdevums", block[0].strip(), re.I) else block


def extract_audio_assets(block: list[str]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in block:
        for match in re.finditer(r'<source\s+src="([^"]+\.mp3)"', line):
            path = normalize_asset_path(match.group(1))
            if path in seen:
                continue
            seen.add(path)
            assets.append(
                {
                    "type": "audio",
                    "path": path,
                    "label": asset_label(path),
                }
            )
        for match in re.finditer(r"\[Audio failsafe link\]\(([^)]+\.mp3)\)", line):
            path = normalize_asset_path(match.group(1))
            if path in seen:
                continue
            seen.add(path)
            assets.append(
                {
                    "type": "audio",
                    "path": path,
                    "label": asset_label(path),
                }
            )
    return assets


def extract_image_assets(block: list[str]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in block:
        for match in re.finditer(r"!\[([^\]]*)\]\((Attachments/[^)]+\.(?:png|jpg|jpeg|webp))\)", line, re.I):
            path = normalize_asset_path(match.group(2))
            if path in seen:
                continue
            seen.add(path)
            assets.append(
                {
                    "type": "image",
                    "path": path,
                    "label": clean_answer(match.group(1) or asset_label(path)),
                }
            )
    return assets


def extract_task_assets(block: list[str]) -> list[dict[str, Any]]:
    return extract_audio_assets(block) + extract_image_assets(block)


def extract_assets(lines: list[str], path: Path) -> dict[str, list[dict[str, Any]]]:
    audio: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    seen_audio: set[str] = set()
    seen_images: set[str] = set()

    for line in lines:
        for match in re.finditer(r'<source\s+src="([^"]+\.mp3)"', line):
            asset_path = normalize_asset_path(match.group(1))
            if asset_path in seen_audio:
                continue
            seen_audio.add(asset_path)
            audio.append({"type": "audio", "path": asset_path, "label": asset_label(asset_path)})
        for match in re.finditer(r"\[Audio failsafe link\]\(([^)]+\.mp3)\)", line):
            asset_path = normalize_asset_path(match.group(1))
            if asset_path in seen_audio:
                continue
            seen_audio.add(asset_path)
            audio.append({"type": "audio", "path": asset_path, "label": asset_label(asset_path)})
        for match in re.finditer(r"!\[([^\]]*)\]\((Attachments/[^)]+\.(?:png|jpg|jpeg|webp))\)", line, re.I):
            asset_path = normalize_asset_path(match.group(2))
            if asset_path in seen_images:
                continue
            seen_images.add(asset_path)
            images.append(
                {
                    "type": "image",
                    "path": asset_path,
                    "label": clean_answer(match.group(1) or asset_label(asset_path)),
                }
            )

    if not audio:
        audio = fallback_audio(path)
    if not images:
        images = fallback_images(path)
    return {"audio": audio, "images": images}


def fallback_audio(path: Path) -> list[dict[str, Any]]:
    attachment_root = f"codex/Attachments/{path.stem}"
    files = [
        "klausisanas_1_uzdevums.mp3",
        "klausisanas_2_uzdevums.mp3",
        "klausisanas_3_uzdevums.mp3",
        "runasana_1_jautajumi.mp3",
        "runasana_2_jautajumi.mp3",
        "runasana_3_jautajumi.mp3",
    ]
    return [{"type": "audio", "path": f"{attachment_root}/{file}", "label": asset_label(file)} for file in files]


def fallback_images(path: Path) -> list[dict[str, Any]]:
    attachment_root = f"codex/Attachments/{path.stem}"
    files = [
        "rakstisana_1_attels_1.png",
        "rakstisana_1_attels_2.png",
        "rakstisana_1_attels_3.png",
        "rakstisana_1_attels_4.png",
        "runasana_2_attels_1.png",
        "runasana_2_attels_2.png",
    ]
    return [{"type": "image", "path": f"{attachment_root}/{file}", "label": asset_label(file)} for file in files]


def split_task_blocks(section_lines: list[str]) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    current_task_key = ""
    current_block: list[str] = []
    for line in section_lines:
        task_match = re.match(r"^####\s+(\d+)\.\s*uzdevums", line.strip(), re.I)
        section_match = re.match(r"^###\s+", line.strip())
        if task_match:
            if current_task_key and current_block:
                blocks.append((current_task_key, current_block))
            current_task_key = f"task{task_match.group(1)}"
            current_block = [line]
            continue
        if section_match:
            if current_task_key and current_block:
                blocks.append((current_task_key, current_block))
            current_task_key = ""
            current_block = []
            continue
        if current_task_key:
            current_block.append(line)
    if current_task_key and current_block:
        blocks.append((current_task_key, current_block))
    return blocks


def section_between(lines: list[str], start_heading: str, end_heading_prefixes: list[str]) -> list[str]:
    start = find_heading_index(lines, start_heading)
    if start is None:
        return []
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if any(stripped.startswith(prefix) for prefix in end_heading_prefixes):
            end = index
            break
    return lines[start:end]


def find_heading_index(lines: list[str], heading: str) -> int | None:
    for index, line in enumerate(lines):
        if line.strip() == heading:
            return index
    return None


def extract_title(lines: list[str]) -> str | None:
    for line in lines:
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            return clean_answer(match.group(1))
    return None


def extract_exam_id(path: Path) -> str:
    match = re.search(r"(\d{2})$", path.stem)
    if match:
        return match.group(1)
    return path.stem


def slugify_exam_id(exam_id: str) -> str:
    return f"a2_mock_exam_{exam_id.lower()}"


def skill_from_heading(value: str) -> str:
    normalized = value.lower()
    if "klaus" in normalized:
        return "listening"
    if "las" in normalized:
        return "reading"
    if "rakst" in normalized:
        return "writing"
    if "run" in normalized:
        return "speaking"
    return ""


def skill_minutes(skill: str) -> int:
    return {
        "listening": 25,
        "reading": 30,
        "writing": 35,
        "speaking": 15,
    }[skill]


def task_title(task_key: str) -> str:
    number = task_key.replace("task", "")
    return f"{number}. uzdevums"


def asset_label(path: str) -> str:
    return Path(path).stem.replace("_", " ")


def normalize_asset_path(path: str) -> str:
    if path.startswith("/"):
        path = path.lstrip("/")
    if path.startswith("Attachments/"):
        return f"codex/{path}"
    return path


def asset_exists(asset_path: str, root: Path) -> bool:
    relative = Path(asset_path)
    candidate = root / relative
    return candidate.exists()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", clean_answer(value)).lower()


def clean_answer(value: str) -> str:
    return re.sub(r"\s{2,}", " ", str(value)).strip().replace("–", "-")


def clean_block(lines: list[str]) -> str:
    cleaned = []
    for line in lines:
        if is_asset_line(line):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_asset_line(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith("<audio")
        or stripped.startswith("</audio>")
        or stripped.startswith("[Audio failsafe link]")
        or stripped.startswith("![")
        or stripped.startswith("<source ")
    )


def issue(code: str, message: str, path: str, severity: str = "error") -> ValidationIssue:
    return ValidationIssue(code=code, message=message, path=path, severity=severity)


def validate_status(value: str) -> str:
    if value not in WORKFLOW_STATUSES:
        raise ValueError(f"Unsupported workflow status: {value}")
    return value


def to_json(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2)
