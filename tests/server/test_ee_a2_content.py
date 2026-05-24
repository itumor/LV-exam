"""Unit tests for T-063 — Estonian A2 fork content pack.

Covers the T-063 deliverable:

* (1) The EE-A2 placeholder manifest at
      ``content/exams/EE/A2/EE_A2_Mock_Exam_01.exam.json`` validates
      against the shared exam schema.
* (2) The manifest declares ``language: "et"`` and ``level: "A2"`` with
      the A2 9/15 pass threshold (Estonian A2 reuses the same CEFR-A2
      rule as Latvian naturalization).
* (3) The four skill sections sum to 60 points (15 per skill).
* (4) The T-025 seed exposes an ``EE-A2`` level row with the four
      Estonian skill rows attached.
* (5) Every audio asset referenced by the manifest exists on disk so
      the catalog endpoint never serves a 404 for the EE fork.
* (6) The original Latvian + Lithuanian seed thresholds are untouched.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EE_DIR = ROOT / "content" / "exams" / "EE" / "A2"
EE_MANIFESTS = sorted(EE_DIR.glob("EE_A2_Mock_Exam_*.exam.json"))


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


def _load_schema_a2_direct():
    """Load ``server_app/services/schema_a2.py`` by path — keeps tests hermetic."""

    spec = importlib.util.spec_from_file_location(
        "schema_a2_direct_t063",
        ROOT / "server_app" / "services" / "schema_a2.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EeA2ManifestSchemaTests(unittest.TestCase):
    """T-063 (1)+(2)+(3): the placeholder manifest is schema-clean."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_validator_module()
        cls.schema = cls.module.load_schema()
        cls.validator = cls.module.build_validator(cls.schema)

    def test_ee_a2_content_pack_ships_at_least_one_exam(self) -> None:
        self.assertGreaterEqual(
            len(EE_MANIFESTS),
            1,
            f"T-063 must ship at least 1 EE-A2 placeholder; found "
            f"{len(EE_MANIFESTS)} at {EE_DIR}",
        )

    def test_every_ee_manifest_validates(self) -> None:
        for path in EE_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                errors = [
                    self.module._format_error(e)
                    for e in self.validator.iter_errors(manifest)
                ]
                self.assertEqual(
                    errors, [],
                    f"{path.name} failed schema: {errors}",
                )

    def test_every_ee_manifest_is_language_et(self) -> None:
        for path in EE_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    manifest["language"], "et",
                    f"{path.name} must declare language='et'",
                )

    def test_every_ee_manifest_is_a2_level_with_9_threshold(self) -> None:
        for path in EE_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["level"], "A2")
                self.assertEqual(
                    manifest["scoring"]["minimum_per_skill"], 9,
                    "Estonian A2 uses the same 9/15 threshold as Latvian A2",
                )

    def test_every_ee_manifest_totals_60_points(self) -> None:
        for path in EE_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["scoring"]["total_points"], 60)
                for skill, pts in manifest["scoring"]["skill_points"].items():
                    self.assertEqual(
                        pts, 15,
                        f"{path.name}: {skill} must equal 15 points (got {pts})",
                    )

    def test_ee_manifest_has_four_skill_sections(self) -> None:
        expected = {"listening", "reading", "writing", "speaking"}
        for path in EE_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                skills = {s["skill"] for s in manifest.get("sections") or []}
                self.assertEqual(skills, expected)

    def test_per_skill_task_points_sum_to_15(self) -> None:
        for path in EE_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                for section in manifest["sections"]:
                    total = sum(int(t["points_max"]) for t in section["tasks"])
                    self.assertEqual(
                        total, 15,
                        f"{path.name} {section['skill']} sums to {total}, "
                        "want 15",
                    )

    def test_ee_audio_assets_exist_on_disk(self) -> None:
        """T-063 (5): listening + speaking audio placeholders ship on disk."""

        for path in EE_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                referenced: list[str] = []
                for section in manifest["sections"]:
                    for task in section["tasks"]:
                        for asset in task.get("audio_assets") or []:
                            referenced.append(asset["path"])
                # Listening section must reference at least one MP3.
                listening = next(
                    (s for s in manifest["sections"] if s["skill"] == "listening"),
                    None,
                )
                self.assertIsNotNone(listening)
                listening_audio = [
                    asset["path"]
                    for task in listening["tasks"]
                    for asset in (task.get("audio_assets") or [])
                ]
                self.assertTrue(
                    listening_audio,
                    "EE listening must reference at least one MP3",
                )
                for rel in referenced:
                    abs_path = (ROOT / rel).resolve()
                    self.assertTrue(
                        abs_path.is_file(),
                        f"missing EE audio file: {abs_path}",
                    )
                    self.assertTrue(
                        rel.endswith(".mp3"),
                        f"asset {rel} must be an .mp3",
                    )


class EeA2SeedTests(unittest.TestCase):
    """T-063 (4)+(6): the T-025 catalog includes EE-A2 with four skill rows."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema_a2 = _load_schema_a2_direct()

    def test_ee_a2_level_row_present(self) -> None:
        seed_rows = {row[1]: row for row in self.schema_a2._SEED_LEVELS}
        self.assertIn(
            "EE-A2", seed_rows,
            "T-063: EE-A2 must be present in the level seed",
        )
        # (level_id, code, name, total_points, min_per_skill)
        self.assertEqual(seed_rows["EE-A2"][3], 60)
        self.assertEqual(
            seed_rows["EE-A2"][4], 9,
            "Estonian A2 must keep the 9/15 threshold (matches Latvian A2)",
        )

    def test_ee_a2_skills_seeded(self) -> None:
        ee_skill_codes = {
            row[2] for row in self.schema_a2._SEED_SKILLS if row[1] == "EE-A2"
        }
        self.assertEqual(
            ee_skill_codes,
            {"listening", "reading", "writing", "speaking"},
            "EE-A2 must seed all four CEFR skills",
        )

    def test_ee_a2_skill_names_are_estonian(self) -> None:
        """The localized ``name`` column must hold the Estonian translations."""

        names_by_code = {
            row[2]: row[3]
            for row in self.schema_a2._SEED_SKILLS
            if row[1] == "EE-A2"
        }
        self.assertEqual(names_by_code["listening"], "Kuulamine")
        self.assertEqual(names_by_code["reading"], "Lugemine")
        self.assertEqual(names_by_code["writing"], "Kirjutamine")
        self.assertEqual(names_by_code["speaking"], "Rääkimine")

    def test_latvian_and_lithuanian_rows_are_not_disturbed(self) -> None:
        """Regression: T-063 must not change A2/B1/B2/LT-A2 seed thresholds."""

        seed_rows = {row[1]: row for row in self.schema_a2._SEED_LEVELS}
        self.assertEqual(seed_rows["A2"][4], 9)
        self.assertEqual(seed_rows["B1"][4], 12)
        self.assertEqual(seed_rows["B2"][4], 15)
        self.assertEqual(seed_rows["LT-A2"][4], 9)


if __name__ == "__main__":
    unittest.main()
