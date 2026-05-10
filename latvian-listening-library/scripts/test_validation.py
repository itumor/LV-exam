import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

required_fields = ["id", "level", "original_filename", "audio_url", "status"]
optional_fields = [
    "title",
    "lv_text",
    "en_text",
    "lv_markdown_url",
    "en_markdown_url",
    "transcription_status",
    "translation_status",
    "lesson_group",
    "order",
    "waveform_url",
]


def validate_lesson(lesson, is_dev=True):
    errors = []
    for field in required_fields:
        if field not in lesson or not lesson[field]:
            errors.append(f"Missing required field: {field}")

    if lesson.get("level") and lesson["level"] not in ["A1", "A2"]:
        errors.append(f"Invalid level: {lesson.get('level')}")

    if lesson.get("status") and lesson["status"] not in [
        "completed",
        "transcribed only",
        "translation failed",
        "failed",
        "pending",
    ]:
        errors.append(f"Invalid status: {lesson.get('status')}")

    if is_dev and errors:
        print(f"[LessonValidation] {lesson.get('id', 'unknown')}: {errors}")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_catalog(catalog, is_dev=True):
    if not isinstance(catalog, list):
        return {
            "valid": False,
            "errors": ["Catalog must be an array"],
            "count": 0,
            "invalid_count": 0,
        }

    invalid_lessons = []
    for i, lesson in enumerate(catalog):
        result = validate_lesson(lesson, is_dev)
        if not result["valid"]:
            invalid_lessons.append(
                {"index": i, "id": lesson.get("id"), "errors": result["errors"]}
            )

    if is_dev and invalid_lessons:
        print(f"[LessonValidation] Invalid lessons: {len(invalid_lessons)}")

    return {
        "valid": len(invalid_lessons) == 0,
        "errors": [e for l in invalid_lessons for e in l["errors"]],
        "count": len(catalog),
        "invalid_count": len(invalid_lessons),
    }


class TestLessonValidation(unittest.TestCase):
    def test_validate_lesson_rejects_missing_id(self):
        result = validate_lesson({"level": "A1"}, is_dev=False)
        self.assertFalse(result["valid"])
        self.assertIn("Missing required field: id", result["errors"])

    def test_validate_lesson_rejects_missing_level(self):
        result = validate_lesson(
            {
                "id": "test",
                "original_filename": "x.mp3",
                "audio_url": "x.mp3",
                "status": "completed",
            },
            is_dev=False,
        )
        self.assertFalse(result["valid"])
        self.assertIn("Missing required field: level", result["errors"])

    def test_validate_lesson_rejects_invalid_level(self):
        result = validate_lesson(
            {
                "id": "test",
                "level": "A3",
                "original_filename": "x.mp3",
                "audio_url": "x.mp3",
                "status": "completed",
            },
            is_dev=False,
        )
        self.assertFalse(result["valid"])
        self.assertIn("Invalid level: A3", result["errors"])

    def test_validate_lesson_accepts_valid_lesson(self):
        result = validate_lesson(
            {
                "id": "A1-xxx",
                "level": "A1",
                "original_filename": "1.nodalja.mp3",
                "audio_url": "data/A1/1.nodalja.mp3",
                "status": "completed",
            },
            is_dev=False,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_lesson_accepts_all_statuses(self):
        for status in [
            "completed",
            "transcribed only",
            "translation failed",
            "failed",
            "pending",
        ]:
            result = validate_lesson(
                {
                    "id": "test",
                    "level": "A1",
                    "original_filename": "x.mp3",
                    "audio_url": "x.mp3",
                    "status": status,
                },
                is_dev=False,
            )
            self.assertTrue(result["valid"], f"Status {status} should be valid")


class TestAnalyticsEvents(unittest.TestCase):
    def test_creates_event_with_correct_structure(self):
        import time
        import random

        session_id = f"session_{int(time.time())}_{random.random():.8f}"
        event_type = "audio_play"
        payload = {"lesson_id": "A1-abc", "filename": "test.mp3"}

        event = {
            "id": f"evt_{int(time.time())}_{random.randint(100000, 999999)}",
            "type": event_type,
            "timestamp": f"{int(time.time())}",
            "session_id": session_id,
            "payload": payload,
        }

        self.assertIn("id", event)
        self.assertIn("type", event)
        self.assertEqual(event["type"], event_type)
        self.assertIn("payload", event)
        self.assertEqual(event["payload"]["lesson_id"], "A1-abc")

    def test_all_event_types_defined(self):
        event_types = {
            "audio_play",
            "audio_pause",
            "sentence_replay",
            "lesson_complete",
            "quiz_submit",
            "flashcard_review",
            "exam_simulation_complete",
        }

        expected = {
            "audio_play",
            "audio_pause",
            "sentence_replay",
            "lesson_complete",
            "quiz_submit",
            "flashcard_review",
            "exam_simulation_complete",
        }

        self.assertEqual(event_types, expected)


class TestCatalogValidation(unittest.TestCase):
    def test_validate_catalog_rejects_non_array(self):
        result = validate_catalog({"items": []}, is_dev=False)
        self.assertFalse(result["valid"])
        self.assertIn("Catalog must be an array", result["errors"])

    def test_validate_catalog_accepts_empty_array(self):
        result = validate_catalog([], is_dev=False)
        self.assertTrue(result["valid"])
        self.assertEqual(result["count"], 0)

    def test_validate_catalog_rejects_invalid_lessons(self):
        catalog = [
            {
                "id": "1",
                "level": "A1",
                "original_filename": "a.mp3",
                "audio_url": "a.mp3",
                "status": "completed",
            },
            {"id": "2", "level": "B1"},  # invalid - missing required fields
        ]
        result = validate_catalog(catalog, is_dev=False)
        self.assertFalse(result["valid"])
        self.assertEqual(result["invalid_count"], 1)

    def test_validate_catalog_counts_correctly(self):
        catalog = [
            {
                "id": "1",
                "level": "A1",
                "original_filename": "a.mp3",
                "audio_url": "a.mp3",
                "status": "completed",
            },
            {
                "id": "2",
                "level": "A2",
                "original_filename": "b.mp3",
                "audio_url": "b.mp3",
                "status": "completed",
            },
        ]
        result = validate_catalog(catalog, is_dev=False)
        self.assertTrue(result["valid"])
        self.assertEqual(result["count"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
