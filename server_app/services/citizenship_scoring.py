"""Citizenship (naturalisation) exam scoring (T-071).

The Latvian naturalisation exam has a different shape from CEFR exams:

* Three sections instead of four:
    - ``history``       (10 questions, 10 points)
    - ``constitution``  (10 questions, 10 points)
    - ``language``      (15 points across listening/reading/writing tasks)

* Pass rule is dual-section rather than per-skill:
    1. History + Constitution combined  ≥ ``minimum_history_constitution``  (default 12/20).
    2. Language section                  ≥ ``minimum_language``              (default 9/15).
   Both thresholds must be met. Failing either fails the entire exam,
   regardless of total raw points.

This module is the single source of truth used by:

* the citizenship-exam frontend (``latvian-a2-exam-app/citizenship-exam.*``)
  when the learner clicks Submit;
* attempt persistence in :mod:`server_app.services.attempts` for any future
  CITIZENSHIP-level attempt rows;
* the citizenship tests in ``tests/test_citizenship_exam.py``.

The functions here are intentionally pure (no DB / IO): callers pass in the
already-loaded manifest and an answer dict. Tests can exercise the pass /
partial-pass / fail logic in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


# Default thresholds — match the manifest defaults but can be overridden by
# the manifest's ``scoring.minimum_per_section`` block.
DEFAULT_MIN_HISTORY_CONSTITUTION = 12  # of 20 combined
DEFAULT_MIN_LANGUAGE = 9               # of 15

CITIZENSHIP_LEVEL = "CITIZENSHIP"
CITIZENSHIP_SECTIONS = ("history", "constitution", "language")


@dataclass(slots=True)
class CitizenshipScore:
    """Per-section + overall scoring outcome for a citizenship attempt."""

    history: int = 0
    constitution: int = 0
    language: int = 0
    # subjective_pending counts language points that are not yet decided
    # (e.g. the free-text writing task awaiting manual / AI evaluation).
    subjective_pending_language: int = 0
    minimum_history_constitution: int = DEFAULT_MIN_HISTORY_CONSTITUTION
    minimum_language: int = DEFAULT_MIN_LANGUAGE
    # Detailed per-question hits for UI display.
    items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def history_constitution_combined(self) -> int:
        return self.history + self.constitution

    @property
    def total(self) -> int:
        return self.history + self.constitution + self.language

    @property
    def history_constitution_passed(self) -> bool:
        return self.history_constitution_combined >= self.minimum_history_constitution

    @property
    def language_passed(self) -> bool:
        return self.language >= self.minimum_language

    @property
    def passed(self) -> bool:
        """Citizenship pass rule (T-071): BOTH dual-section thresholds met.

        Partial pass — e.g. crushing history+constitution but failing
        language, or vice versa — is a FAIL. This mirrors the real
        Latvian naturalisation exam: each section has its own bar.
        """

        return self.history_constitution_passed and self.language_passed

    @property
    def failure_reason(self) -> str | None:
        if self.passed:
            return None
        if not self.history_constitution_passed and not self.language_passed:
            return "both_sections_below_minimum"
        if not self.history_constitution_passed:
            return "history_constitution_below_minimum"
        return "language_below_minimum"

    def as_dict(self) -> dict[str, Any]:
        return {
            "history": self.history,
            "constitution": self.constitution,
            "history_constitution_combined": self.history_constitution_combined,
            "language": self.language,
            "subjective_pending_language": self.subjective_pending_language,
            "total": self.total,
            "minimum_history_constitution": self.minimum_history_constitution,
            "minimum_language": self.minimum_language,
            "history_constitution_passed": self.history_constitution_passed,
            "language_passed": self.language_passed,
            "passed": self.passed,
            "failure_reason": self.failure_reason,
            "items": self.items,
        }


def _normalize_answer(raw: Any) -> str:
    """Lower-case + strip an answer for objective comparison."""

    if raw is None:
        return ""
    if isinstance(raw, bool):
        return "true" if raw else "false"
    return str(raw).strip().lower()


def _correct_set(question: dict[str, Any]) -> list[str]:
    """Normalised list of acceptable answers for a question."""

    answers = question.get("correct_answers")
    if not answers:
        single = question.get("correct_answer")
        if single is None:
            return []
        answers = [single]
    return [_normalize_answer(a) for a in answers if a is not None and str(a).strip() != ""]


def _iter_tasks(section: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for task in section.get("tasks") or []:
        if isinstance(task, dict):
            yield task


def _score_objective_question(
    question: dict[str, Any],
    learner_answer: Any,
) -> tuple[bool, int]:
    """Return (is_correct, points). Objective questions are worth 1 point each
    in citizenship; the language ``gap_fill`` task is also 1 point per blank."""

    correct = _correct_set(question)
    if not correct:
        return False, 0
    submitted = _normalize_answer(learner_answer)
    if not submitted:
        return False, 1  # answered nothing — counted as wrong but 1 point possible
    return submitted in correct, 1


def score_citizenship_attempt(
    manifest: dict[str, Any],
    answers: dict[str, Any] | None,
    *,
    subjective_awards: dict[str, dict[str, int]] | None = None,
) -> CitizenshipScore:
    """Score a citizenship attempt against the manifest.

    Parameters
    ----------
    manifest
        The CITIZENSHIP-level exam manifest (loaded JSON).
    answers
        Nested dict keyed by ``section_skill -> task_key -> question_number ->
        learner answer``. Question numbers may be strings or ints — both are
        accepted.
    subjective_awards
        Optional manually-awarded points for subjective tasks (e.g. the
        language writing task). Shape:
        ``{"language": {"task3": <points>}}``. Awards beyond ``points_max``
        are clamped.
    """

    if not isinstance(manifest, dict):
        raise TypeError("manifest must be a dict")
    if manifest.get("level") != CITIZENSHIP_LEVEL:
        raise ValueError(
            f"score_citizenship_attempt requires level=CITIZENSHIP, got {manifest.get('level')!r}"
        )

    scoring_block = manifest.get("scoring") or {}
    min_per_section = scoring_block.get("minimum_per_section") or {}
    score = CitizenshipScore(
        minimum_history_constitution=int(
            min_per_section.get(
                "history_constitution_combined", DEFAULT_MIN_HISTORY_CONSTITUTION
            )
        ),
        minimum_language=int(
            min_per_section.get("language", DEFAULT_MIN_LANGUAGE)
        ),
    )

    answers = answers or {}
    awards = subjective_awards or {}

    for section in manifest.get("sections") or []:
        if not isinstance(section, dict):
            continue
        skill = section.get("skill")
        if skill not in CITIZENSHIP_SECTIONS:
            continue
        section_answers = answers.get(skill) or {}
        section_awards = awards.get(skill) or {}
        section_points = 0

        for task in _iter_tasks(section):
            task_key = task.get("task_key")
            task_answers = section_answers.get(task_key) or {}
            task_points = 0
            scoring_mode = task.get("scoring_mode", "objective")

            for question in task.get("questions") or []:
                qnum = question.get("number")
                qnum_keys = (str(qnum), qnum) if qnum is not None else ()
                submitted: Any = None
                for k in qnum_keys:
                    if isinstance(task_answers, dict) and k in task_answers:
                        submitted = task_answers[k]
                        break

                kind = question.get("kind", "")
                if scoring_mode == "subjective" or kind in {
                    "subjective",
                    "subjective_sentence",
                }:
                    # Subjective question — only counted via subjective_awards.
                    score.items.append(
                        {
                            "section": skill,
                            "task": task_key,
                            "question": qnum,
                            "kind": kind,
                            "correct": None,
                            "points_max": 1,
                            "awarded": None,
                            "subjective_pending": True,
                        }
                    )
                    continue

                is_correct, possible = _score_objective_question(
                    question, submitted
                )
                awarded = possible if is_correct else 0
                task_points += awarded
                score.items.append(
                    {
                        "section": skill,
                        "task": task_key,
                        "question": qnum,
                        "kind": kind,
                        "correct": is_correct,
                        "points_max": possible,
                        "awarded": awarded,
                    }
                )

            # Subjective bulk awards (writing task etc.).
            if scoring_mode == "subjective":
                task_max = int(task.get("points_max") or 0)
                awarded = int(section_awards.get(task_key, 0) or 0)
                awarded = max(0, min(awarded, task_max))
                task_points += awarded
                # Track unawarded language subjective capacity so the UI can
                # flag "AI scoring pending" instead of treating it as a fail.
                if skill == "language":
                    score.subjective_pending_language += max(
                        0, task_max - awarded
                    )

            section_points += task_points

        # Clamp to section max so a buggy manifest can't sneak in extra points.
        section_max = int(section.get("points_max") or 0)
        if section_max > 0:
            section_points = min(section_points, section_max)

        if skill == "history":
            score.history = section_points
        elif skill == "constitution":
            score.constitution = section_points
        elif skill == "language":
            score.language = section_points

    return score


def explain_score(score: CitizenshipScore) -> str:
    """Human-readable summary for the UI / API."""

    parts = [
        f"History+Constitution: {score.history_constitution_combined}/20 "
        f"(min {score.minimum_history_constitution})",
        f"Language: {score.language}/15 (min {score.minimum_language})",
    ]
    if score.passed:
        parts.append("Result: PASS")
    else:
        reason = score.failure_reason or "unknown"
        parts.append(f"Result: FAIL ({reason})")
    return " | ".join(parts)
