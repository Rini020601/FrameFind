"""
Automated Test Suite for Screenrecord Manager
Tests database FTS5 queries, Apple Vision OCR, categorization,
privacy redactor, video processing, and indexing pipeline.
"""

import os
import tempfile
import unittest
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from core.database import SearchDatabase
from core.classifier import CaptureClassifier
from core.redactor import PrivacyRedactor
from core.video import VideoProcessor
from core.indexer import IndexerPipeline
from core.ocr import get_ocr_engine
from core.namer import SmartNamer


class TestScreenrecordManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_library.db")
        self.db = SearchDatabase(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_insert_and_fts5_search(self):
        """Test inserting records and querying FTS5 with ranked snippets."""
        record_id = self.db.insert_or_update_record({
            "file_path": "/fake/path/test_recording.mov",
            "file_name": "test_recording.mov",
            "file_type": "video",
            "duration_sec": 120.5,
            "width": 1920,
            "height": 1080,
            "file_size_bytes": 1024 * 1024 * 50,
            "app_name": "VS Code",
            "category": "Code & Terminal",
            "thumbnail_path": ""
        })
        self.assertGreater(record_id, 0)

        # Insert events
        self.db.insert_event({
            "record_id": record_id,
            "timestamp_sec": 42.0,
            "frame_idx": 1260,
            "ocr_text": "TypeError: Cannot read properties of undefined (reading 'token')",
            "bounding_boxes": [],
            "is_keyframe": 1
        })

        self.db.insert_event({
            "record_id": record_id,
            "timestamp_sec": 75.0,
            "frame_idx": 2250,
            "ocr_text": "const userProfile = await fetch('/api/user');",
            "bounding_boxes": [],
            "is_keyframe": 1
        })

        # Test search for "TypeError"
        results = self.db.search("TypeError")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["record_id"], record_id)
        self.assertEqual(results[0]["timestamp_sec"], 42.0)
        self.assertIn("<mark>TypeError</mark>", results[0]["ocr_snippet"])

        # Test search for "fetch"
        results_fetch = self.db.search("fetch")
        self.assertEqual(len(results_fetch), 1)
        self.assertEqual(results_fetch[0]["timestamp_sec"], 75.0)

    def test_classifier(self):
        """Test categorization heuristics for Code, Slides, Meetings."""
        code_text = "def calculate_revenue(users):\n    return users * 49.99\nTraceback (most recent call last):"
        cat, app = CaptureClassifier.classify_text(code_text)
        self.assertEqual(cat, "Code & Terminal")

        slide_text = "Q3 Product Roadmap\n- Strategic Deliverables\n- Executive Summary\n- Key Takeaways"
        cat_slide, _ = CaptureClassifier.classify_text(slide_text)
        self.assertEqual(cat_slide, "Slides & Presentation")

        meeting_text = "Zoom Meeting with Engineering Team\nParticipants (14)\nMute / Unmute\nScreen sharing"
        cat_meet, app_meet = CaptureClassifier.classify_text(meeting_text)
        self.assertEqual(cat_meet, "Meeting & Chat")
        self.assertEqual(app_meet, "Zoom")

    def test_privacy_redactor(self):
        """Test detection and blurring of API keys, tokens, emails."""
        secret_text = "Connecting with API Key: sk-proj1234567890abcdefghijklmn and contact support@company.com"
        findings = PrivacyRedactor.detect_secrets(secret_text)
        self.assertGreaterEqual(len(findings), 2)
        labels = [f["label"] for f in findings]
        self.assertIn("OpenAI / API Key", labels)
        self.assertIn("Email Address", labels)

        # Test blurring on image
        test_img = Image.new("RGB", (400, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(test_img)
        draw.text((20, 50), "sk-proj1234567890abcdefghijklmn", fill=(0, 0, 0))

        boxes = [{
            "text": "sk-proj1234567890abcdefghijklmn",
            "box": [0.05, 0.25, 0.7, 0.15]
        }]
        redacted_img, notes = PrivacyRedactor.redact_frame(test_img, boxes)
        self.assertEqual(len(notes), 1)
        self.assertIn("Redacted OpenAI / API Key", notes[0])

    def test_apple_vision_ocr(self):
        """Test native Apple Vision OCR on a generated test image."""
        img = Image.new("RGB", (600, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((40, 70), "ANTIGRAVITY PYTHON OCR TEST 2026", fill=(0, 0, 0))

        ocr = get_ocr_engine()
        text, boxes = ocr.recognize_image(img)
        # Verify text was recognized by Apple Vision
        self.assertTrue(any("ANTIGRAVITY" in t or "OCR" in t or "TEST" in t for t in text.split()))
        self.assertGreater(len(boxes), 0)

    def test_video_generation_and_indexing_pipeline(self):
        """Generate a short 2-second test video and index it through the full pipeline."""
        video_path = os.path.join(self.temp_dir.name, "sample_clip.mp4")
        w, h = 640, 360
        fps = 10
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(video_path, fourcc, fps, (w, h))

        # 20 frames total (2 seconds)
        for i in range(20):
            frame = np.full((h, w, 3), 240, dtype=np.uint8)
            # Add text on frame
            cv2.putText(
                frame, f"Frame {i}: ErrorCode 404 Not Found",
                (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 200), 2
            )
            out.write(frame)
        out.release()

        # Run Indexing Pipeline
        pipeline = IndexerPipeline(db=self.db)
        rec_id = pipeline.index_file(video_path)
        self.assertIsNotNone(rec_id)

        # Check DB record
        record = self.db.get_record(rec_id)
        self.assertEqual(record["file_name"], "sample_clip.mp4")
        self.assertEqual(record["file_type"], "video")

        # Check events
        events = self.db.get_record_events(rec_id)
        self.assertGreater(len(events), 0)

        # Search for "ErrorCode" or "Found"
        hits = self.db.search("ErrorCode")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0]["record_id"], rec_id)

    def test_smart_namer(self):
        """Test auto-naming based on OCR text content."""
        error_ocr = [
            "VS Code - main.py",
            "Traceback (most recent call last):",
            "TypeError: cannot unpack non-iterable NoneType object"
        ]
        title = SmartNamer.generate_title(error_ocr, app_name="VS Code", category="Code & Terminal")
        self.assertIn("VS Code", title)
        self.assertIn("TypeError", title)

        slide_ocr = ["Q3 Product Roadmap", "Strategic Milestones"]
        slide_title = SmartNamer.generate_title(slide_ocr, app_name="Slides", category="Slides & Presentation")
        self.assertIn("Roadmap", slide_title)

        # Test physical file rename
        dummy_file = os.path.join(self.temp_dir.name, "Screen Recording 2026-11-15 at 10.00.00.mov")
        with open(dummy_file, "w") as f:
            f.write("content")

        new_path = SmartNamer.rename_recording_file(dummy_file, title)
        self.assertTrue(os.path.exists(new_path))
        self.assertFalse(os.path.exists(dummy_file))
        self.assertIn("TypeError", os.path.basename(new_path))

    def test_automatic_finder_renaming_flow(self):
        """Simulate real macOS screen recording landing in Finder and getting auto-renamed."""
        # 1. Create a file with generic macOS screen recording name
        rec_path = os.path.join(self.temp_dir.name, "Screen Recording 2026-11-15 at 20.15.30.mp4")
        w, h = 640, 360
        fps = 10
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(rec_path, fourcc, fps, (w, h))
        for _ in range(15):
            frame = np.full((h, w, 3), 30, dtype=np.uint8)
            cv2.putText(frame, "VS Code - server.py", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (220, 220, 220), 2)
            cv2.putText(frame, "SyntaxError: unexpected EOF while parsing", (40, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 255), 2)
            out.write(frame)
        out.release()

        self.assertTrue(os.path.exists(rec_path))

        # 2. Pipeline runs with auto_rename=True (as the background daemon does)
        pipeline = IndexerPipeline(db=self.db, auto_rename=True)
        rec_id = pipeline.index_file(rec_path)
        self.assertIsNotNone(rec_id)

        # 3. Verify original generic name NO LONGER EXISTS on disk
        self.assertFalse(os.path.exists(rec_path))

        # 4. Verify file was renamed on disk to content-based title
        record = self.db.get_record(rec_id)
        new_path = record["file_path"]
        self.assertTrue(os.path.exists(new_path))
        self.assertIn("SyntaxError", record["file_name"])


if __name__ == "__main__":
    unittest.main()
