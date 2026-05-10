from __future__ import annotations

import unittest

import server


class StaticSecurityTests(unittest.TestCase):
    def test_static_allowlist_blocks_source_and_data_files(self) -> None:
        for path in (
            "/server.py",
            "/billing.py",
            "/data/billing.sqlite3",
            "/.env",
            "/migrations/20260505_attempt_persistence.sql",
            "/codex/A2_Mock_Exam_01.md",
            "/latvian-a2-exam-app/assets/",
        ):
            self.assertFalse(server.is_public_static_path(path), path)

    def test_static_allowlist_keeps_app_and_media_assets_public(self) -> None:
        for path in (
            "/latvian-a2-exam-app/",
            "/latvian-a2-exam-app/index.html",
            "/latvian-a2-exam-app/app.js",
            "/latvian-a2-exam-app/styles.css",
            "/codex/Attachments/A2_Mock_Exam_01/klausisanas_1_uzdevums.mp3",
            "/codex/Attachments/A2_Mock_Exam_01/rakstisana_1_attels_1.png",
        ):
            self.assertTrue(server.is_public_static_path(path), path)

    def test_student_markdown_strips_teacher_material(self) -> None:
        markdown = """
# Demo

## Student Version
Visible task.

## Answer Key
**1. uzdevums:** 1. a

## Listening Transcripts
Secret transcript.

## Writing Model Answers
Secret model.
""".strip()

        public = server.student_exam_markdown(markdown)

        self.assertIn("Visible task.", public)
        self.assertNotIn("Answer Key", public)
        self.assertNotIn("Secret transcript", public)
        self.assertNotIn("Secret model", public)


if __name__ == "__main__":
    unittest.main()
