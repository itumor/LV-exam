"""Unit tests for T-071 — Naturalizācijas (citizenship) exam pack.

Covers the deliverables in the T-071 plan:

* (1) The shipped NAT manifest at ``content/exams/NAT/NAT_Exam_01.exam.json``
      passes the JSON-schema validator.
* (2) Schema enforces CITIZENSHIP-specific shape:
      - 3 sections (history, constitution, language) with 10/10/15 points,
      - total_points = 35,
      - dual-section ``minimum_per_section`` block (history_constitution_combined
        + language) instead of CEFR's flat ``minimum_per_skill``.
      - regression guard: CEFR-shaped manifest at level=CITIZENSHIP must fail.
* (3) Pass-rule scoring:
      - Both sections meet minimum -> PASS.
      - History+Constitution meets minimum but language fails -> FAIL (partial pass rejection).
      - Language meets minimum but History+Constitution fails -> FAIL.
      - Both fail -> FAIL with combined failure reason.

These tests are hermetic: they parse the schema/JSON manifests directly
and exercise ``server_app.services.citizenship_scoring`` in isolation.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NAT_DIR = ROOT / "content" / "exams" / "NAT"
NAT_MANIFESTS = sorted(NAT_DIR.glob("NAT_Exam_*.exam.json"))


def _load_validator_module():
    if "validate_exam_content" in sys.modules:
        return sys.modules["validate_exam_content"]
    spec = importlib.util.spec_from_file_location(
        "validate_exam_content",
        ROOT / "scripts" / "validate_exam_content.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_exam_content"] = module
    spec.loader.exec_module(module)
    return module


def _nat_manifest_template() -> dict:
    """Minimal but schema-valid CITIZENSHIP manifest for negative tests."""

    def hc_section(skill: str) -> dict:
        return {
            "skill": skill,
            "title": f"{skill} section",
            "points_max": 10,
            "minutes": 20,
            "tasks": [
                {
                    "task_key": "task1",
                    "title": f"{skill} task1",
                    "scoring_mode": "objective",
                    "points_max": 10,
                    "instruction": "answer 10 questions",
                    "questions": [
                        {
                            "number": i,
                            "prompt": f"Q{i}",
                            "kind": "multiple_choice",
                            "options": [
                                {"label": "a", "text": "A"},
                                {"label": "b", "text": "B"},
                            ],
                            "correct_answers": ["a"],
                        }
                        for i in range(1, 11)
                    ],
                }
            ],
        }

    language_section = {
        "skill": "language",
        "title": "Latviešu valodas zināšanu minimums",
        "points_max": 15,
        "minutes": 45,
        "tasks": [
            {
                "task_key": "task1",
                "title": "reading",
                "scoring_mode": "objective",
                "points_max": 5,
                "instruction": "answer",
                "questions": [
                    {
                        "number": i,
                        "prompt": f"Q{i}",
                        "kind": "multiple_choice",
                        "options": [
                            {"label": "a", "text": "A"},
                            {"label": "b", "text": "B"},
                        ],
                        "correct_answers": ["a"],
                    }
                    for i in range(1, 6)
                ],
            },
            {
                "task_key": "task2",
                "title": "inflection",
                "scoring_mode": "objective",
                "points_max": 5,
                "instruction": "fill",
                "questions": [
                    {
                        "number": i,
                        "prompt": f"({i}) word",
                        "kind": "gap_fill",
                        "correct_answers": ["x"],
                    }
                    for i in range(1, 6)
                ],
            },
            {
                "task_key": "task3",
                "title": "writing",
                "scoring_mode": "subjective",
                "points_max": 5,
                "instruction": "write",
                "questions": [
                    {
                        "number": 1,
                        "prompt": "Write about Latvia",
                        "kind": "subjective",
                        "minimum_words": 30,
                    }
                ],
            },
        ],
    }

    return {
        "schema_version": "1.0",
        "version": "2026.05.0",
        "exam_id": "nat-test",
        "slug": "nat-test",
        "title": "Citizenship test exam",
        "level": "CITIZENSHIP",
        "language": "lv",
        "status": "draft",
        "content_version": 1,
        "scoring": {
            "total_points": 35,
            "section_points": {
                "history": 10,
                "constitution": 10,
                "language": 15,
            },
            "minimum_per_section": {
                "history_constitution_combined": 12,
                "language": 9,
            },
            "task_point_allocation": {
                "history":      {"task1": 10},
                "constitution": {"task1": 10},
                "language":     {"task1": 5, "task2": 5, "task3": 5},
            },
            "pass_rule": {
                "kind": "citizenship_dual_section",
                "history_constitution_combined_min": 12,
                "language_min": 9,
            },
        },
        "sections": [
            hc_section("history"),
            hc_section("constitution"),
            language_section,
        ],
    }


def _build_answers(
    *,
    history_correct: int,
    constitution_correct: int,
    language_reading_correct: int,
    language_gap_correct: int,
) -> dict:
    """Build a learner-answer dict against the manifest template.

    The template uses correct_answer='a' for every objective MC question and
    correct_answer='x' for every gap_fill; we mark the requested number as
    correct and the rest as wrong.
    """

    def mc_block(n_correct: int, total: int) -> dict:
        out = {}
        for i in range(1, total + 1):
            out[i] = "a" if i <= n_correct else "b"
        return out

    def gap_block(n_correct: int, total: int) -> dict:
        out = {}
        for i in range(1, total + 1):
            out[i] = "x" if i <= n_correct else "wrong"
        return out

    return {
        "history": {"task1": mc_block(history_correct, 10)},
        "constitution": {"task1": mc_block(constitution_correct, 10)},
        "language": {
            "task1": mc_block(language_reading_correct, 5),
            "task2": gap_block(language_gap_correct, 5),
            "task3": {1: "Es vēlos kļūt par Latvijas pilsoni jo..."},
        },
    }


class CitizenshipShippedManifestTests(unittest.TestCase):
    """T-071 (1)+(2): the shipped NAT manifest passes the schema."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_validator_module()
        cls.schema = cls.module.load_schema()
        cls.validator = cls.module.build_validator(cls.schema)

    def test_nat_content_pack_has_at_least_one_exam(self) -> None:
        self.assertGreaterEqual(
            len(NAT_MANIFESTS),
            1,
            f"T-071 ships at least one CITIZENSHIP exam at {NAT_DIR}",
        )

    def test_every_nat_manifest_validates(self) -> None:
        for path in NAT_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                errors = [
                    self.module._format_error(e)
                    for e in self.validator.iter_errors(manifest)
                ]
                self.assertEqual(
                    errors, [], f"{path.name} failed schema: {errors}"
                )

    def test_every_nat_manifest_is_citizenship_level(self) -> None:
        for path in NAT_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["level"], "CITIZENSHIP")

    def test_every_nat_manifest_has_dual_section_pass_rule(self) -> None:
        for path in NAT_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                scoring = manifest["scoring"]
                self.assertEqual(scoring["total_points"], 35)
                self.assertEqual(scoring["section_points"]["history"], 10)
                self.assertEqual(scoring["section_points"]["constitution"], 10)
                self.assertEqual(scoring["section_points"]["language"], 15)
                self.assertIn("minimum_per_section", scoring)
                self.assertIn(
                    "history_constitution_combined",
                    scoring["minimum_per_section"],
                )
                self.assertIn("language", scoring["minimum_per_section"])

    def test_every_nat_manifest_has_three_sections(self) -> None:
        expected = {"history", "constitution", "language"}
        for path in NAT_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                skills = {s["skill"] for s in manifest["sections"]}
                self.assertEqual(skills, expected)

    def test_history_has_10_questions(self) -> None:
        for path in NAT_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                history = next(
                    s for s in manifest["sections"] if s["skill"] == "history"
                )
                qs = history["tasks"][0]["questions"]
                self.assertEqual(
                    len(qs), 10, f"History section in {path.name} must have 10 questions"
                )

    def test_constitution_has_10_questions(self) -> None:
        for path in NAT_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                consti = next(
                    s for s in manifest["sections"] if s["skill"] == "constitution"
                )
                qs = consti["tasks"][0]["questions"]
                self.assertEqual(
                    len(qs), 10,
                    f"Constitution section in {path.name} must have 10 questions",
                )


class CitizenshipSchemaNegativeTests(unittest.TestCase):
    """T-071 (2) regression guards on the schema."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_validator_module()
        cls.schema = cls.module.load_schema()
        cls.validator = cls.module.build_validator(cls.schema)

    def test_citizenship_level_rejects_cefr_skills(self) -> None:
        """A CEFR-shaped manifest at level=CITIZENSHIP must fail validation."""

        manifest = _nat_manifest_template()
        # Replace one section's skill with a CEFR one and watch it explode.
        manifest["sections"][0]["skill"] = "listening"
        errors = list(self.validator.iter_errors(manifest))
        self.assertTrue(
            errors,
            "CITIZENSHIP manifest with a CEFR 'listening' section must fail schema",
        )

    def test_citizenship_total_points_must_be_35(self) -> None:
        manifest = _nat_manifest_template()
        manifest["scoring"]["total_points"] = 60
        errors = list(self.validator.iter_errors(manifest))
        self.assertTrue(
            errors,
            "CITIZENSHIP manifest with total_points=60 must fail schema",
        )

    def test_a2_still_requires_minimum_per_skill_9(self) -> None:
        """Regression guard: A2 still requires the flat CEFR rule."""

        # Build a tiny A2 manifest with the wrong threshold.
        from copy import deepcopy

        def cefr_section(skill: str) -> dict:
            return {
                "skill": skill,
                "title": f"{skill} section",
                "points_max": 15,
                "minutes": 20,
                "tasks": [
                    {
                        "task_key": "task1",
                        "title": f"{skill} task1",
                        "scoring_mode": "objective",
                        "points_max": 15,
                        "instruction": "test",
                        "questions": [
                            {
                                "number": 1,
                                "prompt": "x",
                                "kind": "multiple_choice",
                                "options": [
                                    {"label": "a", "text": "A"},
                                    {"label": "b", "text": "B"},
                                ],
                                "correct_answers": ["a"],
                            }
                        ],
                    }
                ],
            }

        manifest = {
            "schema_version": "1.0",
            "version": "2026.05.0",
            "exam_id": "a2-test",
            "title": "A2 test",
            "level": "A2",
            "language": "lv",
            "status": "draft",
            "content_version": 1,
            "scoring": {
                "total_points": 60,
                "skill_points": {
                    "listening": 15, "reading": 15, "writing": 15, "speaking": 15,
                },
                "minimum_per_skill": 12,  # WRONG for A2 (must be 9)
            },
            "sections": [
                cefr_section("listening"),
                cefr_section("reading"),
                cefr_section("writing"),
                cefr_section("speaking"),
            ],
        }
        errors = list(self.validator.iter_errors(manifest))
        self.assertTrue(
            errors,
            "A2 manifest with minimum_per_skill=12 must still fail schema",
        )


class CitizenshipScoringTests(unittest.TestCase):
    """T-071 (3): dual-section pass rule + partial-pass rejection."""

    def setUp(self) -> None:
        from server_app.services import citizenship_scoring

        self.scorer = citizenship_scoring
        self.manifest = _nat_manifest_template()

    def test_perfect_objective_score_passes(self) -> None:
        answers = _build_answers(
            history_correct=10,
            constitution_correct=10,
            language_reading_correct=5,
            language_gap_correct=5,
        )
        score = self.scorer.score_citizenship_attempt(self.manifest, answers)
        self.assertEqual(score.history, 10)
        self.assertEqual(score.constitution, 10)
        self.assertEqual(score.language, 10)  # subjective task3 unawarded yet
        # 10/10 hc combined >= 12; language 10/15 >= 9 ⇒ PASS
        self.assertTrue(score.history_constitution_passed)
        self.assertTrue(score.language_passed)
        self.assertTrue(score.passed)
        self.assertIsNone(score.failure_reason)

    def test_minimum_borderline_pass(self) -> None:
        """At exactly the dual thresholds: 12/20 + 9/15 ⇒ PASS."""

        # 6 history + 6 constitution = 12 combined; 9 language objective
        answers = _build_answers(
            history_correct=6,
            constitution_correct=6,
            language_reading_correct=5,
            language_gap_correct=4,
        )
        score = self.scorer.score_citizenship_attempt(self.manifest, answers)
        self.assertEqual(score.history_constitution_combined, 12)
        self.assertEqual(score.language, 9)
        self.assertTrue(score.passed)

    def test_partial_pass_history_only_fails(self) -> None:
        """Strong history+constitution but weak language ⇒ FAIL.

        This is the core T-071 deliverable (5): partial pass rejection.
        Even with 20/20 on knowledge sections, failing language fails the exam.
        """

        answers = _build_answers(
            history_correct=10,
            constitution_correct=10,
            language_reading_correct=2,
            language_gap_correct=2,
        )
        score = self.scorer.score_citizenship_attempt(self.manifest, answers)
        self.assertEqual(score.history_constitution_combined, 20)
        self.assertEqual(score.language, 4)
        self.assertTrue(score.history_constitution_passed)
        self.assertFalse(score.language_passed)
        self.assertFalse(score.passed, "20/20 knowledge + 4/15 language must fail")
        self.assertEqual(score.failure_reason, "language_below_minimum")

    def test_partial_pass_language_only_fails(self) -> None:
        """Strong language but weak history+constitution ⇒ FAIL."""

        answers = _build_answers(
            history_correct=3,
            constitution_correct=3,
            language_reading_correct=5,
            language_gap_correct=5,
        )
        score = self.scorer.score_citizenship_attempt(self.manifest, answers)
        self.assertEqual(score.history_constitution_combined, 6)
        self.assertEqual(score.language, 10)
        self.assertFalse(score.history_constitution_passed)
        self.assertTrue(score.language_passed)
        self.assertFalse(score.passed, "6/20 knowledge + 10/15 language must fail")
        self.assertEqual(
            score.failure_reason, "history_constitution_below_minimum"
        )

    def test_below_minimum_in_both_fails(self) -> None:
        answers = _build_answers(
            history_correct=2,
            constitution_correct=2,
            language_reading_correct=1,
            language_gap_correct=1,
        )
        score = self.scorer.score_citizenship_attempt(self.manifest, answers)
        self.assertEqual(score.history_constitution_combined, 4)
        self.assertEqual(score.language, 2)
        self.assertFalse(score.passed)
        self.assertEqual(score.failure_reason, "both_sections_below_minimum")

    def test_subjective_writing_award_pushes_language_pass(self) -> None:
        """Writing task can lift language from FAIL to PASS via subjective award."""

        answers = _build_answers(
            history_correct=10,
            constitution_correct=10,
            language_reading_correct=4,  # 4/5
            language_gap_correct=3,      # 3/5 — total objective = 7/10
        )
        # 7/15 language alone fails; an award of 3+ for task3 lifts to 10/15.
        no_award = self.scorer.score_citizenship_attempt(self.manifest, answers)
        self.assertFalse(no_award.language_passed, "objective-only language 7/15 fails")
        with_award = self.scorer.score_citizenship_attempt(
            self.manifest, answers,
            subjective_awards={"language": {"task3": 3}},
        )
        self.assertTrue(
            with_award.language_passed,
            "writing award should lift language >= 9",
        )
        self.assertTrue(with_award.passed)

    def test_subjective_award_clamped_to_task_max(self) -> None:
        answers = _build_answers(
            history_correct=10,
            constitution_correct=10,
            language_reading_correct=5,
            language_gap_correct=5,
        )
        # Try to over-award subjective task (max 5).
        score = self.scorer.score_citizenship_attempt(
            self.manifest, answers,
            subjective_awards={"language": {"task3": 999}},
        )
        # Language section is capped at 15 total.
        self.assertLessEqual(score.language, 15)

    def test_rejects_non_citizenship_manifest(self) -> None:
        manifest = deepcopy(self.manifest)
        manifest["level"] = "B1"
        with self.assertRaises(ValueError):
            self.scorer.score_citizenship_attempt(manifest, {})

    def test_score_dict_serialises_pass_metadata(self) -> None:
        answers = _build_answers(
            history_correct=10,
            constitution_correct=10,
            language_reading_correct=5,
            language_gap_correct=5,
        )
        score = self.scorer.score_citizenship_attempt(self.manifest, answers)
        payload = score.as_dict()
        self.assertIn("passed", payload)
        self.assertIn("history_constitution_combined", payload)
        self.assertIn("language", payload)
        self.assertIn("minimum_history_constitution", payload)
        self.assertIn("minimum_language", payload)
        self.assertIn("failure_reason", payload)
        self.assertEqual(payload["passed"], True)


if __name__ == "__main__":
    unittest.main()
