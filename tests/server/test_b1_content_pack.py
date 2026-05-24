"""Unit tests for T-060 — B1 exam content pack.

Covers the deliverables in the T-060 plan:

* (1) The three shipped B1 manifests at ``content/exams/B1/*.exam.json``
      pass the JSON-schema validator.
* (2) The B1 12/15 pass rule is enforced by the schema:
      - level=B1 with minimum_per_skill=12 must pass,
      - level=B1 with minimum_per_skill=9 must fail,
      - level=A2 still requires minimum_per_skill=9 (regression guard).
* (3) Every B1 manifest has at least 12 points per skill in scoring metadata.
* (4) The B1 entries are exposed by ``built_in_exam_catalog`` so the
      existing ``/api/exams/catalog`` endpoint returns them.
* (5) The T-025 seed encodes ``min_per_skill=12`` for the B1 level row.

These tests are hermetic: they parse the schema/JSON manifests directly
and call into ``scripts/validate_exam_content.py`` helpers. The catalog
test imports ``server_app.core`` so it requires Python 3.10+ (matches CI;
``exam_bank`` uses ``@dataclass(slots=True)``).
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

B1_DIR = ROOT / "content" / "exams" / "B1"
B1_MANIFESTS = sorted(B1_DIR.glob("B1_Mock_Exam_*.exam.json"))


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


def _b1_manifest_template() -> dict:
    """Return a tiny but schema-valid B1 manifest for negative tests."""

    def section(skill: str) -> dict:
        return {
            "skill": skill,
            "title": f"{skill} section",
            "points_max": 15,
            "minutes": 25,
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

    return {
        "schema_version": "1.0",
        "version": "2026.05.0",
        "exam_id": "b1-test",
        "slug": "b1-test",
        "title": "B1 test exam",
        "level": "B1",
        "language": "lv",
        "status": "draft",
        "content_version": 1,
        "scoring": {
            "total_points": 60,
            "skill_points": {
                "listening": 15,
                "reading": 15,
                "writing": 15,
                "speaking": 15,
            },
            "minimum_per_skill": 12,
            "task_point_allocation": {
                "listening": {"task1": 15},
                "reading":   {"task1": 15},
                "writing":   {"task1": 15},
                "speaking":  {"task1": 15},
            },
        },
        "sections": [
            section("listening"),
            section("reading"),
            section("writing"),
            section("speaking"),
        ],
    }


class B1ShippedManifestTests(unittest.TestCase):
    """T-060 (1): the three B1 manifests under content/exams/B1/ pass the schema."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_validator_module()
        cls.schema = cls.module.load_schema()
        cls.validator = cls.module.build_validator(cls.schema)

    def test_b1_content_pack_has_three_exams(self) -> None:
        self.assertEqual(
            len(B1_MANIFESTS),
            3,
            f"T-060 ships exactly 3 B1 mock exams; found {len(B1_MANIFESTS)} "
            f"at {B1_DIR}",
        )

    def test_every_b1_manifest_validates(self) -> None:
        for path in B1_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                errors = [
                    self.module._format_error(e)
                    for e in self.validator.iter_errors(manifest)
                ]
                self.assertEqual(errors, [], f"{path.name} failed schema: {errors}")

    def test_every_b1_manifest_is_level_b1(self) -> None:
        for path in B1_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["level"], "B1")

    def test_every_b1_manifest_has_12_minimum_per_skill(self) -> None:
        """T-060 (3): B1 pass threshold is 12/15 per skill."""

        for path in B1_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    manifest["scoring"]["minimum_per_skill"],
                    12,
                    f"{path.name} must set minimum_per_skill=12 (B1 pass rule)",
                )
                self.assertEqual(manifest["scoring"]["total_points"], 60)
                for skill, pts in manifest["scoring"]["skill_points"].items():
                    self.assertEqual(pts, 15, f"{path.name}: {skill}={pts}, want 15")

    def test_every_b1_manifest_has_four_skill_sections(self) -> None:
        expected = {"listening", "reading", "writing", "speaking"}
        for path in B1_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                skills = {s["skill"] for s in manifest.get("sections") or []}
                self.assertEqual(
                    skills, expected, f"{path.name} sections={skills}"
                )

    def test_every_b1_listening_task_has_audio_assets(self) -> None:
        """T-060 (3): placeholder MP3 paths must be referenced from listening tasks."""

        for path in B1_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                listening = next(
                    (
                        s for s in manifest["sections"]
                        if s["skill"] == "listening"
                    ),
                    None,
                )
                self.assertIsNotNone(listening)
                for task in listening["tasks"]:
                    audio = task.get("audio_assets") or []
                    self.assertTrue(
                        audio,
                        f"{path.name} listening {task['task_key']} "
                        "must reference at least one MP3",
                    )
                    for clip in audio:
                        self.assertTrue(
                            clip["path"].endswith(".mp3"),
                            f"audio asset {clip['path']} must be an mp3",
                        )
                        # Audio file must exist on disk (placeholder MP3s ship
                        # in the repo so the catalog endpoint never 404s).
                        abs_path = (ROOT / clip["path"]).resolve()
                        self.assertTrue(
                            abs_path.is_file(),
                            f"missing audio file: {abs_path}",
                        )

    def test_per_skill_task_points_sum_to_15(self) -> None:
        """T-060: the cross-task invariant survives — every skill totals 15."""

        for path in B1_MANIFESTS:
            with self.subTest(manifest=path.name):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                for section in manifest["sections"]:
                    total = sum(int(t["points_max"]) for t in section["tasks"])
                    self.assertEqual(
                        total,
                        15,
                        f"{path.name} {section['skill']} task points "
                        f"sum to {total}, want 15",
                    )


class B1PassRuleSchemaTests(unittest.TestCase):
    """T-060 (2): the 12/15 rule is enforced and the 9/15 rule for A2 still holds."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_validator_module()
        cls.schema = cls.module.load_schema()
        cls.validator = cls.module.build_validator(cls.schema)

    def _errors(self, manifest: dict) -> list[str]:
        return [
            self.module._format_error(e)
            for e in self.validator.iter_errors(manifest)
        ]

    def test_b1_with_minimum_12_passes(self) -> None:
        manifest = _b1_manifest_template()
        self.assertEqual(self._errors(manifest), [])

    def test_b1_with_minimum_9_fails(self) -> None:
        manifest = _b1_manifest_template()
        manifest["scoring"]["minimum_per_skill"] = 9
        errors = self._errors(manifest)
        self.assertTrue(
            any("12" in e for e in errors),
            f"B1 must reject minimum_per_skill=9; got {errors}",
        )

    def test_b1_with_minimum_15_fails(self) -> None:
        manifest = _b1_manifest_template()
        manifest["scoring"]["minimum_per_skill"] = 15
        errors = self._errors(manifest)
        self.assertTrue(
            any("12" in e for e in errors),
            f"B1 must reject minimum_per_skill=15; got {errors}",
        )

    def test_a2_still_requires_minimum_9(self) -> None:
        """Regression: changing B1 rules must not loosen A2."""

        manifest = _b1_manifest_template()
        manifest["level"] = "A2"
        manifest["scoring"]["minimum_per_skill"] = 12  # invalid for A2
        errors = self._errors(manifest)
        self.assertTrue(
            any("9" in e for e in errors),
            f"A2 must reject minimum_per_skill=12; got {errors}",
        )


class B1CatalogIntegrationTests(unittest.TestCase):
    """T-060 (4): B1 entries flow through ``built_in_exam_catalog``."""

    def test_built_in_catalog_contains_three_b1_exams(self) -> None:
        from server_app import core as server_core

        catalog = server_core.built_in_exam_catalog()
        b1_entries = [
            entry for entry in catalog
            if str(entry.get("id", "")).startswith("b1-")
        ]
        self.assertEqual(
            len(b1_entries),
            3,
            f"expected 3 B1 entries; got {[e['id'] for e in b1_entries]}",
        )
        for entry in b1_entries:
            self.assertEqual(entry["status"], "published")
            self.assertEqual(entry["manifest"]["level"], "B1")
            md = entry["manifest"]["sourcePath"]
            self.assertTrue(
                (ROOT / md).is_file(),
                f"student markdown must exist on disk: {md}",
            )
            mp = entry["manifest"]["manifestPath"]
            self.assertTrue(
                (ROOT / mp).is_file(),
                f"JSON manifest must exist on disk: {mp}",
            )


class B1SeedThresholdTests(unittest.TestCase):
    """T-060 (5): the T-025 seed encodes B1 min_per_skill=12.

    We load ``server_app/services/schema_a2.py`` by path (bypassing the
    ``server_app`` package __init__) so the seed-row assertions never
    depend on the rest of the import graph.
    """

    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "schema_a2_direct", ROOT / "server_app" / "services" / "schema_a2.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.schema_a2 = module

    def test_b1_seed_row_uses_min_per_skill_12(self) -> None:
        seed_rows = {row[1]: row for row in self.schema_a2._SEED_LEVELS}
        self.assertIn("B1", seed_rows, "B1 must be present in the seed")
        # (level_id, code, name, total_points, min_per_skill)
        self.assertEqual(seed_rows["B1"][3], 60, "B1 total_points must be 60")
        self.assertEqual(
            seed_rows["B1"][4],
            12,
            "T-060: B1 min_per_skill must be 12 (12/15 pass rule)",
        )
        # Regression: A2 still uses 9, B2 still uses 15.
        self.assertEqual(seed_rows["A2"][4], 9)
        self.assertEqual(seed_rows["B2"][4], 15)

    def test_b1_skills_seeded(self) -> None:
        b1_skill_codes = {
            row[2] for row in self.schema_a2._SEED_SKILLS if row[1] == "B1"
        }
        self.assertEqual(
            b1_skill_codes,
            {"listening", "reading", "writing", "speaking"},
            "B1 must seed all four skills (T-025 + T-060)",
        )


if __name__ == "__main__":
    unittest.main()
