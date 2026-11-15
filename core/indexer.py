"""
Indexer Pipeline Module for Screenrecord Manager
Orchestrates metadata extraction, keyframe sampling, Apple Vision OCR,
categorization, and database persistence.
"""

import os
import logging
from typing import Optional, Callable, Dict, Any
from PIL import Image

from .database import SearchDatabase
from .video import VideoProcessor, THUMBNAIL_DIR
from .ocr import get_ocr_engine
from .classifier import CaptureClassifier
from .namer import SmartNamer

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTS = {".mov", ".mp4", ".m4v"}
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


class IndexerPipeline:
    def __init__(self, db: Optional[SearchDatabase] = None, auto_rename: bool = True):
        self.db = db or SearchDatabase()
        self.auto_rename = auto_rename
        self.video_processor = VideoProcessor(sample_interval_sec=2.0, scene_change_thresh=0.15)
        self.ocr_engine = get_ocr_engine()

    def index_file(
        self,
        file_path: str,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Optional[int]:
        """
        Index a single video recording or screenshot.
        :param file_path: Absolute path to media file
        :param progress_cb: Optional callback func(pct: float, status_msg: str)
        :return: record_id or None
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        ext = os.path.splitext(file_path)[1].lower()
        if ext in SUPPORTED_VIDEO_EXTS:
            return self._index_video(file_path, progress_cb)
        elif ext in SUPPORTED_IMAGE_EXTS:
            return self._index_screenshot(file_path, progress_cb)
        else:
            logger.warning(f"Unsupported file format: {file_path}")
            return None

    def _index_video(
        self,
        file_path: str,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Optional[int]:
        if progress_cb:
            progress_cb(0.05, f"Reading metadata: {os.path.basename(file_path)}")

        try:
            meta = self.video_processor.get_metadata(file_path)
        except Exception as e:
            logger.error(f"Failed to read video metadata: {e}")
            return None

        # Insert placeholder record
        record_data = {
            "file_path": file_path,
            "file_name": meta["file_name"],
            "file_type": "video",
            "duration_sec": meta["duration_sec"],
            "width": meta["width"],
            "height": meta["height"],
            "file_size_bytes": meta["file_size_bytes"],
            "app_name": "macOS",
            "category": "General",
            "thumbnail_path": ""
        }
        record_id = self.db.insert_or_update_record(record_data)

        # Generate main video thumbnail
        thumb_path = self.video_processor.generate_video_thumbnail(file_path, record_id)
        if thumb_path:
            self.db.conn.execute(
                "UPDATE records SET thumbnail_path = ? WHERE id = ?", (thumb_path, record_id)
            )
            self.db.conn.commit()

        if progress_cb:
            progress_cb(0.15, "Sampling keyframes and running Apple Vision OCR...")

        total_frames = meta["frame_count"]
        fps = meta["fps"] or 30.0
        all_detected_text = []
        collected_events = []
        event_count = 0

        for frame_info in self.video_processor.extract_keyframes(file_path, record_id):
            timestamp_sec = frame_info["timestamp_sec"]
            pil_image = frame_info["pil_image"]
            frame_idx = frame_info["frame_idx"]

            # Run Apple Vision OCR
            ocr_text, boxes = self.ocr_engine.recognize_image(pil_image)

            # Only store event if text or scene change was detected
            if ocr_text.strip():
                all_detected_text.append(ocr_text)
                collected_events.append({
                    "timestamp_sec": timestamp_sec,
                    "ocr_text": ocr_text,
                    "bounding_boxes": boxes
                })
                self.db.insert_event({
                    "record_id": record_id,
                    "timestamp_sec": timestamp_sec,
                    "frame_idx": frame_idx,
                    "ocr_text": ocr_text,
                    "audio_text": "",
                    "bounding_boxes": boxes,
                    "is_keyframe": 1 if frame_info["is_scene_change"] else 0,
                    "frame_thumb_path": frame_info["thumb_path"]
                })
                event_count += 1

            # Update progress
            pct = 0.15 + 0.80 * min(1.0, frame_idx / max(1, total_frames))
            if progress_cb:
                mins = int(timestamp_sec // 60)
                secs = int(timestamp_sec % 60)
                progress_cb(pct, f"Indexed at {mins:02d}:{secs:02d} ({event_count} events found)")

        # Auto-classify based on aggregated text
        combined_text = "\n".join(all_detected_text[:20])
        category, inferred_app = CaptureClassifier.classify_text(combined_text)

        with self.db.conn:
            self.db.conn.execute("""
                UPDATE records SET category = ?, app_name = ? WHERE id = ?
            """, (category, inferred_app, record_id))

        # Content-based smart renaming
        filename = os.path.basename(file_path)
        is_generic_name = (
            filename.startswith("Screen Recording") or
            filename.startswith("ScreenShot") or
            filename.startswith("Screen Shot")
        )
        if self.auto_rename and is_generic_name:
            smart_title = SmartNamer.generate_title(
                all_detected_text, inferred_app, category, file_path, events=collected_events
            )
            try:
                new_path = SmartNamer.rename_recording_file(file_path, smart_title)
                if new_path != file_path:
                    self.db.update_record_file_path(record_id, new_path, os.path.basename(new_path))
                    file_path = new_path
                    logger.info(f"Auto-renamed recording to: {os.path.basename(new_path)}")
            except Exception as e:
                logger.warning(f"Auto-rename failed: {e}")

        if progress_cb:
            progress_cb(1.0, f"Done! Indexed {event_count} chapters ({category})")

        return record_id

    def _index_screenshot(
        self,
        file_path: str,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Optional[int]:
        if progress_cb:
            progress_cb(0.1, f"Analyzing screenshot: {os.path.basename(file_path)}")

        try:
            pil_img = Image.open(file_path)
            w, h = pil_img.size
        except Exception as e:
            logger.error(f"Cannot open screenshot {file_path}: {e}")
            return None

        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

        # Run OCR
        if progress_cb:
            progress_cb(0.4, "Running Apple Vision OCR...")
        ocr_text, boxes = self.ocr_engine.recognize_image(pil_img)

        # Categorize
        category, inferred_app = CaptureClassifier.classify_text(ocr_text)

        record_data = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "file_type": "screenshot",
            "duration_sec": 0.0,
            "width": w,
            "height": h,
            "file_size_bytes": file_size,
            "app_name": inferred_app,
            "category": category,
            "thumbnail_path": file_path
        }
        record_id = self.db.insert_or_update_record(record_data)

        # Insert single-frame event at timestamp 0.0
        self.db.insert_event({
            "record_id": record_id,
            "timestamp_sec": 0.0,
            "frame_idx": 0,
            "ocr_text": ocr_text,
            "audio_text": "",
            "bounding_boxes": boxes,
            "is_keyframe": 1,
            "frame_thumb_path": file_path
        })

        # Content-based smart renaming for screenshots
        filename = os.path.basename(file_path)
        is_generic_name = (
            filename.startswith("Screen Recording") or
            filename.startswith("ScreenShot") or
            filename.startswith("Screen Shot")
        )
        if self.auto_rename and is_generic_name:
            smart_title = SmartNamer.generate_title(
                [ocr_text], inferred_app, category, file_path,
                events=[{"ocr_text": ocr_text, "bounding_boxes": boxes}]
            )
            try:
                new_path = SmartNamer.rename_recording_file(file_path, smart_title)
                if new_path != file_path:
                    self.db.update_record_file_path(record_id, new_path, os.path.basename(new_path))
                    file_path = new_path
                    logger.info(f"Auto-renamed screenshot to: {os.path.basename(new_path)}")
            except Exception as e:
                logger.warning(f"Auto-rename failed: {e}")

        if progress_cb:
            progress_cb(1.0, f"Screenshot indexed ({category})")

        return record_id
