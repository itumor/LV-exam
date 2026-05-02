from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from exam_bank import import_and_validate, import_exam_markdown, validate_exam_manifest


ROOT = Path(__file__).resolve().parents[1]


class ExamBankTests(unittest.TestCase):
    def test_imports_current_exam_into_structured_manifest(self) -> None:
        manifest = import_exam_markdown(ROOT / "codex" / "A2_Mock_Exam_01.md")
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["exam_id"], "01")
        self.assertEqual(manifest["status"], "draft")
        self.assertEqual(manifest["scoring"]["total_points"], 60)
        self.assertEqual(len(manifest["sections"]), 4)
        listening = next(section for section in manifest["sections"] if section["skill"] == "listening")
        self.assertEqual(listening["tasks"][0]["questions"][0]["options"][0]["label"], "a")
        writing = next(section for section in manifest["sections"] if section["skill"] == "writing")
        self.assertEqual(len(writing["tasks"][0]["assets"]), 4)
        self.assertIn("answer_key_raw", manifest["references"])

    def test_valid_fixture_passes_validation(self) -> None:
        manifest, issues = import_and_validate(ROOT / "codex" / "A2_Mock_Exam_01.md", root_dir=ROOT)
        self.assertFalse(issues)
        self.assertTrue(manifest["validation"]["valid"])
        self.assertEqual(manifest["validation"]["issues"], [])

    def test_missing_asset_is_reported(self) -> None:
        manifest = import_exam_markdown(ROOT / "codex" / "A2_Mock_Exam_01.md")
        manifest = deepcopy(manifest)
        manifest["sections"][0]["tasks"][0]["assets"][0]["path"] = "codex/Attachments/does-not-exist.mp3"
        issues = validate_exam_manifest(manifest, root_dir=ROOT)
        self.assertTrue(any(issue.code == "broken-asset" for issue in issues))

    def test_duplicate_options_are_reported(self) -> None:
        manifest = import_exam_markdown(ROOT / "codex" / "A2_Mock_Exam_01.md")
        manifest = deepcopy(manifest)
        manifest["sections"][0]["tasks"][0]["questions"][0]["options"][1]["text"] = manifest["sections"][0]["tasks"][0]["questions"][0]["options"][0]["text"]
        issues = validate_exam_manifest(manifest, root_dir=ROOT)
        self.assertTrue(any(issue.code == "duplicate-options" for issue in issues))

    def test_missing_answer_key_is_reported(self) -> None:
        manifest = import_exam_markdown(ROOT / "codex" / "A2_Mock_Exam_01.md")
        manifest = deepcopy(manifest)
        manifest["sections"][0]["tasks"][0]["questions"][0]["correct_answers"] = []
        issues = validate_exam_manifest(manifest, root_dir=ROOT)
        self.assertTrue(any(issue.code == "missing-answer-key" for issue in issues))

    def test_published_status_is_marked_immutable(self) -> None:
        manifest = import_exam_markdown(ROOT / "codex" / "A2_Mock_Exam_01.md", status="published")
        self.assertTrue(manifest["is_immutable"])
        self.assertEqual(manifest["status"], "published")


if __name__ == "__main__":
    unittest.main()
