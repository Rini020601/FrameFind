"""
Automated Test Suite for Screenrecord Manager
Tests database FTS5 queries, Apple Vision OCR, categorization,
privacy redactor, video processing, and indexing pipeline.
"""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from core.database import SearchDatabase
from core.classifier import CaptureClassifier
from core.redactor import PrivacyRedactor
from core.video import VideoProcessor
from core.indexer import IndexerPipeline, is_generic_capture_name
from core.ocr import get_ocr_engine
from core.namer import SmartNamer
from core.summariser import FrameSummariser
from core.auto_renamer import SilentCaptureHandler


class StubOCR:
    """Deterministic OCR for pipeline tests; native Vision has its own smoke test."""

    def __init__(self, text):
        self.text = text

    def recognize_image(self, _image):
        return self.text, [{
            "text": self.text,
            "confidence": 1.0,
            "box": [0.15, 0.2, 0.7, 0.08],
        }]


class TestScreenrecordManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_library.db")
        self.db = SearchDatabase(db_path=self.db_path)

    def tearDown(self):
        self.db.conn.close()
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

        spotify_text = "Spotify Your Library Playlists Daily Mix"
        _, spotify_app = CaptureClassifier.classify_text(spotify_text)
        self.assertEqual(spotify_app, "Spotify")

        calendar_text = "November 2026\nSun\nMon\nTue\nWed\nThu\nFri\nSat"
        _, calendar_app = CaptureClassifier.classify_text(calendar_text)
        self.assertEqual(calendar_app, "Calendar")

        photos_text = "Photos\nLibrary\nAll Photos\n26-30 Mar 2025"
        _, photos_app = CaptureClassifier.classify_text(photos_text)
        self.assertEqual(photos_app, "Photos")

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
        if not text or not boxes:
            self.skipTest("Apple Vision OCR is unavailable in this execution environment")
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
        pipeline.ocr_engine = StubOCR("ErrorCode 404 Not Found")
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

    def test_frame_summariser_uses_cross_frame_salience(self):
        events = [
            {"ocr_text": "Sunrise Planner Daily Goal Tracker"},
            {"ocr_text": "Sunrise Planner Daily Goal Tracker"},
            {"ocr_text": "Sunrise Planner Calendar Daily Goal Tracker"},
        ]
        summary = FrameSummariser.summarise(
            events,
            exclude_words={"sunrise", "planner"},
        )
        self.assertEqual(summary, "Daily Goal Tracker")

    def test_frame_summariser_does_not_join_unrelated_ocr_boxes(self):
        boxes = [
            {"text": "XLOOKUP in"},
            {"text": "EXPLORER"},
            {"text": "SCREENRECORD MANAGER"},
            {"text": "Review app-to-backend"},
            {"text": "• Ran ./.venv/bin/python daemon.py status"},
        ]
        events = [{"bounding_boxes": boxes} for _ in range(4)]

        summary = FrameSummariser.summarise(events)

        self.assertEqual(summary, "Review App-To-Backend")

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
        pipeline.ocr_engine = StubOCR(
            "VS Code - server.py\nSyntaxError: unexpected EOF while parsing"
        )
        rec_id = pipeline.index_file(rec_path)
        self.assertIsNotNone(rec_id)

        # 3. Verify original generic name NO LONGER EXISTS on disk
        self.assertFalse(os.path.exists(rec_path))

        # 4. Verify file was renamed on disk to content-based title
        record = self.db.get_record(rec_id)
        new_path = record["file_path"]
        self.assertTrue(os.path.exists(new_path))
        self.assertIn("SyntaxError", record["file_name"])

    def test_screenshot_prefix_is_renamed(self):
        """Modern macOS uses `Screenshot`, which must match the daemon contract."""
        screenshot_path = os.path.join(
            self.temp_dir.name, "Screenshot 2026-11-21 at 19.18.05.png"
        )
        Image.new("RGB", (800, 500), color="white").save(screenshot_path)

        self.assertTrue(is_generic_capture_name(screenshot_path))
        pipeline = IndexerPipeline(db=self.db, auto_rename=True)
        pipeline.ocr_engine = StubOCR("Quarterly Product Roadmap")
        record_id = pipeline.index_file(screenshot_path)

        record = self.db.get_record(record_id)
        self.assertFalse(os.path.exists(screenshot_path))
        self.assertTrue(os.path.exists(record["file_path"]))
        self.assertNotEqual(record["file_name"], os.path.basename(screenshot_path))

    def test_daemon_deduplicates_unchanged_files(self):
        capture_path = os.path.join(
            self.temp_dir.name, "Screenshot 2026-11-21 at 19.18.05.png"
        )
        Image.new("RGB", (100, 100), color="white").save(capture_path)
        handler = SilentCaptureHandler(Mock())
        handler._wait_and_rename = Mock()

        handler._process_file(capture_path)
        handler._process_file(capture_path)

        handler._wait_and_rename.assert_called_once_with(capture_path, app_hint=None)

    def test_daemon_handles_atomic_move_events(self):
        capture_path = os.path.join(
            self.temp_dir.name, "Screenshot 2026-11-21 at 19.18.05.png"
        )
        Image.new("RGB", (100, 100), color="white").save(capture_path)
        handler = SilentCaptureHandler(Mock())
        handler._wait_and_rename = Mock()
        event = Mock(is_directory=False, dest_path=capture_path)

        with patch("core.auto_renamer.get_frontmost_application", return_value=None):
            handler.on_moved(event)

        handler._wait_and_rename.assert_called_once_with(capture_path, app_hint=None)

    def test_smart_namer_prefers_majority_frame_context(self):
        events = [{
            "ocr_text": "One Time Setup Dialog",
            "bounding_boxes": [{
                "text": "One Time Setup Dialog",
                "box": [0.2, 0.2, 0.6, 0.08],
            }],
        }]
        events.extend({
            "ocr_text": "Quarterly Revenue Review",
            "bounding_boxes": [{
                "text": "Quarterly Revenue Review",
                "box": [0.2, 0.2, 0.6, 0.05],
            }],
        } for _ in range(3))

        title = SmartNamer.generate_title(
            [event["ocr_text"] for event in events],
            app_name="Keynote",
            category="Slides & Presentation",
            original_path="Screen Recording 2026-11-21.mov",
            events=events,
        )

        self.assertIn("Quarterly Revenue Review", title)
        self.assertNotIn("One Time Setup", title)

    def test_smart_namer_detects_fullscreen_spotify(self):
        text = (
            "Your Library\nPlaylists\nWhat do you want to play?\n"
            "Christmas Playlists\nSpotify\nDaily Mix"
        )
        events = [{"bounding_boxes": [
            {"text": "What do you want to play?", "box": [0.39, 0.064, 0.13, 0.018]},
            {"text": "Christmas Playlists", "box": [0.32, 0.15, 0.09, 0.018]},
            {"text": "Spotify", "box": [0.59, 0.21, 0.04, 0.02]},
        ]}]

        title = SmartNamer.generate_title(
            [text],
            app_name="macOS",
            category="Doc & Web",
            original_path="Screenshot 2026-11-21.png",
            events=events,
        )

        self.assertEqual(title, "Spotify - Your Library (2026-11-21)")

    def test_smart_namer_prefers_calendar_month_over_event(self):
        text = (
            "November 2026\nSun\nMon\nTue\nWed\nThu\nFri\nSat\n"
            "Diwali (Deepawali)\nGuru Nanak Gurpurab"
        )
        events = [{"bounding_boxes": [
            {"text": "November 2026", "box": [0.01, 0.09, 0.16, 0.031]},
            {"text": "Guru Nanak Gurpurab", "box": [0.29, 0.62, 0.11, 0.018]},
        ]}]

        title = SmartNamer.generate_title(
            [text],
            app_name="macOS",
            category="Doc & Web",
            original_path="Screenshot 2026-11-21.png",
            events=events,
        )

        self.assertEqual(title, "Calendar - November 2026 (2026-11-21)")

    def test_screenshot_uses_app_then_largest_content_heading(self):
        text = "Chrome\nProducts\nQuarterly Revenue Dashboard\nSettings"
        events = [{"bounding_boxes": [
            {"text": "Chrome", "box": [0.03, 0.01, 0.04, 0.014]},
            {"text": "Products", "box": [0.03, 0.2, 0.06, 0.014]},
            {
                "text": "Quarterly Revenue Dashboard",
                "box": [0.25, 0.22, 0.5, 0.06],
            },
            {"text": "Settings", "box": [0.85, 0.05, 0.06, 0.014]},
        ]}]

        title = SmartNamer.generate_title(
            [text],
            app_name="macOS",
            category="Doc & Web",
            original_path="Screenshot 2026-11-21.png",
            events=events,
        )

        self.assertEqual(
            title,
            "Google Chrome - Quarterly Revenue Dashboard (2026-11-21)",
        )

    def test_screenshot_uses_frontmost_app_hint_when_ocr_has_no_app(self):
        screenshot_path = os.path.join(self.temp_dir.name, "Screenshot 2026-11-21.png")
        Image.new("RGB", (800, 500), color="white").save(screenshot_path)
        pipeline = IndexerPipeline(db=self.db, auto_rename=True)
        pipeline.ocr_engine = StubOCR("Project Timeline")

        record_id = pipeline.index_file(screenshot_path, app_hint="Preview")
        record = self.db.get_record(record_id)

        self.assertEqual(record["app_name"], "Preview")
        self.assertIn("Preview", record["file_name"])

    def test_screenshot_frontmost_app_hint_beats_body_keyword_match(self):
        screenshot_path = os.path.join(self.temp_dir.name, "Screenshot 2026-11-22.png")
        Image.new("RGB", (800, 500), color="white").save(screenshot_path)
        pipeline = IndexerPipeline(db=self.db, auto_rename=True)
        pipeline.ocr_engine = StubOCR("Comparing GitHub and Chrome workflows")

        record_id = pipeline.index_file(screenshot_path, app_hint="Brave Browser")
        record = self.db.get_record(record_id)

        self.assertEqual(record["app_name"], "Brave Browser")
        self.assertTrue(record["file_name"].startswith("Brave Browser - "))

    def test_screenshot_ignores_dock_temperature_and_picks_next_biggest_heading(self):
        events = [{"bounding_boxes": [
            {"text": "Brave", "box": [0.025, 0.01, 0.04, 0.014]},
            {"text": "22 0C", "box": [0.283, 0.936, 0.096, 0.045]},
            {"text": "+ Create", "box": [0.842, 0.161, 0.049, 0.0225]},
            {"text": "System Design Architecture", "box": [0.20, 0.14, 0.45, 0.036]},
            {"text": "Smaller Center Card", "box": [0.42, 0.48, 0.16, 0.020]},
        ]}]

        title = SmartNamer.generate_title(
            ["Brave\n22 0C\n+ Create\nSystem Design Architecture\nSmaller Center Card"],
            app_name="macOS",
            category="Doc & Web",
            original_path="Screenshot 2026-11-22.png",
            events=events,
        )

        self.assertEqual(title, "Brave Browser - System Design Architecture (2026-11-22)")

    def test_browser_home_screen_uses_site_name_over_thumbnail_text(self):
        events = [{"bounding_boxes": [
            {"text": "Brave", "box": [0.036, 0.013, 0.026, 0.0134]},
            {"text": "youtube.com", "box": [0.195, 0.096, 0.060, 0.0134]},
            {"text": "RAMANY", "box": [0.458, 0.380, 0.061, 0.0357]},
            {"text": "Bachelorette", "box": [0.722, 0.451, 0.190, 0.0424]},
        ]}]

        title = SmartNamer.generate_title(
            ["Brave\nyoutube.com\nRAMANY\nBachelorette"],
            app_name="macOS",
            category="Doc & Web",
            original_path="Screenshot 2026-11-22.png",
            events=events,
        )

        self.assertEqual(title, "Brave Browser - YouTube (2026-11-22)")

    def test_youtube_watch_page_ignores_right_sidebar_thumbnails(self):
        events = [{"bounding_boxes": [
            {"text": "Brave", "box": [0.036, 0.013, 0.026, 0.0134]},
            {"text": "youtube.com/watch?v=wXz8AzOxGSM", "box": [0.202, 0.094, 0.176, 0.0156]},
            {"text": "New Bangkok Vlog", "box": [0.717, 0.710, 0.112, 0.0403]},
            {"text": "Bachelorette with My Girls in Phuket | Ahaana Krishna", "box": [0.010, 0.810, 0.330, 0.0225]},
        ]}]

        title = SmartNamer.generate_title(
            ["Brave\nyoutube.com/watch?v=wXz8AzOxGSM\nNew Bangkok Vlog\nBachelorette with My Girls in Phuket | Ahaana Krishna"],
            app_name="macOS",
            category="Doc & Web",
            original_path="Screenshot 2026-11-22.png",
            events=events,
        )

        self.assertTrue(title.startswith("Brave Browser - Bachelorette with My Girls in Phuket"))
        self.assertNotIn("New Bangkok Vlog", title)

    def test_recording_uses_app_and_largest_visible_heading(self):
        events = [
            {"bounding_boxes": [
                {"text": "Brave", "box": [0.036, 0.013, 0.026, 0.0134]},
                {"text": "API Migration Guide", "box": [0.22, 0.18, 0.40, 0.045]},
                {"text": "Hello Class Data", "box": [0.22, 0.45, 0.30, 0.018]},
            ]}
            for _ in range(3)
        ]

        title = SmartNamer.generate_title(
            ["Brave\nAPI Migration Guide\nHello Class Data"] * 3,
            app_name="macOS",
            category="Doc & Web",
            original_path="Screen Recording 2026-11-22.mov",
            events=events,
        )

        self.assertEqual(title, "Brave Browser - API Migration Guide (2026-11-22)")

    def test_spotlight_comment_written_for_finder_search(self):
        from core.indexer import write_spotlight_comment
        import plistlib
        import subprocess

        sample_file = os.path.join(self.temp_dir.name, "sample_video.mov")
        with open(sample_file, "wb") as f:
            f.write(b"dummy")

        ok = write_spotlight_comment(sample_file, ["Marissa 29/08/26", "kadalai Marissa"])
        self.assertTrue(ok)

        out = subprocess.run(
            ["xattr", "-px", "com.apple.metadata:kMDItemFinderComment", sample_file],
            capture_output=True, text=True, check=True,
        )
        comment = plistlib.loads(bytes.fromhex(out.stdout.replace(" ", "").replace("\n", "")))
        self.assertIn("Marissa", comment)
        self.assertIn("kadalai", comment)

    def test_database_wal_and_cascade_delete_no_orphans(self):
        mode = self.db.conn.execute("PRAGMA journal_mode;").fetchone()[0].lower()
        fk = self.db.conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        self.assertEqual(mode, "wal")
        self.assertEqual(fk, 1)

        rec_id = self.db.insert_or_update_record({
            "file_path": "/fake/cascade_test.mov",
            "file_name": "cascade_test.mov",
            "file_type": "video",
        })
        self.db.insert_event({
            "record_id": rec_id,
            "timestamp_sec": 1.0,
            "ocr_text": "CascadeCheckToken",
        })
        self.db.delete_record(rec_id)
        remaining = self.db.conn.execute("SELECT COUNT(*) FROM events WHERE record_id = ?", (rec_id,)).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_rename_recording_file_never_creates_hidden_empty_name(self):
        src = os.path.join(self.temp_dir.name, "Screenshot 2026-11-24.png")
        with open(src, "wb") as f:
            f.write(b"png")
        renamed = SmartNamer.rename_recording_file(src, '///:::***')
        self.assertEqual(os.path.basename(renamed), "Capture.png")
        self.assertTrue(os.path.exists(renamed))

    def test_single_instance_daemon_lock(self):
        from core.auto_renamer import acquire_daemon_lock
        lock_path = os.path.join(self.temp_dir.name, "test_daemon.lock")
        first = acquire_daemon_lock(lock_path)
        self.assertIsNotNone(first)
        second = acquire_daemon_lock(lock_path)
        self.assertIsNone(second)
        first.close()
        third = acquire_daemon_lock(lock_path)
        self.assertIsNotNone(third)
        third.close()

    def test_audio_transcript_alignment_and_batch_fts5_search(self):
        from core.audio import AudioTranscriber
        rec_id = self.db.insert_or_update_record({
            "file_path": "/fake/meeting_demo.mov",
            "file_name": "meeting_demo.mov",
            "file_type": "video",
        })
        events = [
            {"record_id": rec_id, "timestamp_sec": 2.0, "ocr_text": "Slide One", "audio_text": "", "bounding_boxes": []},
            {"record_id": rec_id, "timestamp_sec": 12.0, "ocr_text": "Slide Two", "audio_text": "", "bounding_boxes": []},
        ]
        segments = [
            {"start": 2.5, "end": 4.0, "text": "quarterly kubernetes rollout"},
            {"start": 25.0, "end": 27.0, "text": "standalone spoken remark"},
        ]
        aligned = AudioTranscriber.align_transcript_to_events(segments, events, record_id=rec_id)
        count = self.db.insert_events_batch(aligned)
        self.assertEqual(count, 3)

        hits = self.db.search("kubernetes")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["timestamp_sec"], 2.0)

        hits2 = self.db.search("standalone")
        self.assertEqual(len(hits2), 1)
        self.assertEqual(hits2[0]["timestamp_sec"], 25.0)

    def test_cleanup_orphans_removes_missing_records_and_unreferenced_thumbs(self):
        existing_file = os.path.join(self.temp_dir.name, "keep.png")
        with open(existing_file, "wb") as f:
            f.write(b"ok")
        thumb_dir = os.path.join(self.temp_dir.name, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)
        keep_thumb = os.path.join(thumb_dir, "keep.jpg")
        orphan_thumb = os.path.join(thumb_dir, "orphan.jpg")
        for p in (keep_thumb, orphan_thumb):
            with open(p, "wb") as f:
                f.write(b"jpg")

        keep_id = self.db.insert_or_update_record({
            "file_path": existing_file,
            "file_name": "keep.png",
            "file_type": "screenshot",
            "thumbnail_path": keep_thumb,
        })
        self.db.insert_or_update_record({
            "file_path": os.path.join(self.temp_dir.name, "deleted.mov"),
            "file_name": "deleted.mov",
            "file_type": "video",
        })

        result = self.db.cleanup_orphans(thumbnail_dir=thumb_dir)
        self.assertEqual(result["removed_records"], 1)
        self.assertEqual(result["removed_thumbnails"], 1)
        self.assertIsNotNone(self.db.get_record(keep_id))
        self.assertTrue(os.path.exists(keep_thumb))
        self.assertFalse(os.path.exists(orphan_thumb))

    def test_find_matching_boxes_for_highlight_overlay(self):
        from gui.player_widget import find_matching_boxes
        boxes = [
            {"text": "TypeError: invalid token", "box": [0.1, 0.2, 0.5, 0.04]},
            {"text": "Footer copyright", "box": [0.1, 0.9, 0.3, 0.02]},
        ]
        matched = find_matching_boxes(boxes, "TypeError")
        self.assertEqual(matched, [[0.1, 0.2, 0.5, 0.04]])


    def test_chrome_active_tab_detection(self):
        """
        SmartNamer must pick the ACTIVE Chrome tab (no trailing X) rather than
        background tabs (which Chrome renders with a close-button 'X' that OCR picks up)
        or low-variety noise strings like '000000000'.
        """
        # Simulate OCR bounding-box events from a Chrome recording where:
        #   - "German A1 A2 Study Plan X"  → background tab
        #   - "Python MacBook Air Proje X" → background tab
        #   - "Sunrise Planner"            → ACTIVE tab (no X)
        #   - "Adding an email address X" → background tab
        #   - "000000000"                  → content noise (all same digit)
        events = [
            {
                "bounding_boxes": [
                    # Menu bar: Chrome app name
                    {"text": "Chrome",         "box": [0.03, 0.02, 0.05, 0.015]},
                    # Tab strip (y between 0.028 and 0.078)
                    {"text": "German A1 A2 Study Plan X",  "box": [0.10, 0.056, 0.14, 0.018]},
                    {"text": "Python MacBook Air Proje X", "box": [0.26, 0.056, 0.14, 0.018]},
                    {"text": "Sunrise Planner",            "box": [0.39, 0.056, 0.10, 0.018]},
                    {"text": "Adding an email address X",  "box": [0.52, 0.056, 0.14, 0.018]},
                    # Content noise mid-screen
                    {"text": "000000000",  "box": [0.35, 0.45, 0.30, 0.03]},
                    {"text": "HIGHLIGHTS OF THE YEAR", "box": [0.30, 0.20, 0.40, 0.025]},
                ],
            }
        ]

        title = SmartNamer.generate_title(
            all_ocr_text=["Google Chrome\nSunrise Planner\n000000000\nHIGHLIGHTS OF THE YEAR"],
            app_name="Google Chrome",
            category="Browser",
            original_path="/Users/test/Documents/Screen Recording 2026-11-15 at 16.30.12.mov",
            events=events,
        )

        # Must contain the active tab name
        self.assertIn("Sunrise Planner", title, f"Expected 'Sunrise Planner' in title but got: {title!r}")
        # Must NOT contain the noise string
        self.assertNotIn("000000000", title, f"Noise string '000000000' leaked into title: {title!r}")
        # Must NOT contain background tab text
        self.assertNotIn("German", title, f"Background tab text leaked into title: {title!r}")


if __name__ == "__main__":
    unittest.main()
