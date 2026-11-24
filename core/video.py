"""
Video Processor Module for Screenrecord Manager
Extracts keyframes, detects scene changes (window/slide switches),
and generates thumbnails with precise millisecond timestamps.
"""

import os
import cv2
import numpy as np
from PIL import Image
from typing import List, Dict, Any, Generator, Tuple, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMBNAIL_DIR = os.environ.get(
    "SCREENRECORD_THUMB_DIR",
    os.path.join(PROJECT_ROOT, ".data", "thumbnails")
)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)


class VideoProcessor:
    def __init__(self, sample_interval_sec: float = 2.0, scene_change_thresh: float = 0.18):
        """
        :param sample_interval_sec: Base sampling frequency (seconds between frames)
        :param scene_change_thresh: Pixel difference threshold to detect window/slide transitions
        """
        self.sample_interval_sec = sample_interval_sec
        self.scene_change_thresh = scene_change_thresh

    def get_metadata(self, file_path: str) -> Dict[str, Any]:
        """Read video header information without loading the whole file."""
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {file_path}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration_sec = frame_count / fps if fps > 0 else 0.0
        finally:
            cap.release()

        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

        return {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "fps": fps,
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "duration_sec": round(duration_sec, 2),
            "file_size_bytes": file_size
        }

    def generate_video_thumbnail(self, file_path: str, record_id: int) -> Optional[str]:
        """Extract a cover thumbnail from the first 1-2 seconds of the video."""
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            # Jump to 1 second in to avoid initial black/blank frames
            target_frame = int(min(fps, max(0, cap.get(cv2.CAP_PROP_FRAME_COUNT) - 1)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            success, frame = cap.read()
        finally:
            cap.release()

        if not success or frame is None:
            return None

        thumb_name = f"thumb_rec_{record_id}.jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, thumb_name)

        # Resize to max 320px width preserving aspect ratio
        h, w = frame.shape[:2]
        thumb_w = 320
        thumb_h = int(h * (thumb_w / float(w)))
        resized = cv2.resize(frame, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)

        cv2.imwrite(thumb_path, resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return thumb_path

    def extract_keyframes(
        self, file_path: str, record_id: int
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generator yielding keyframes with:
          - frame_idx: int
          - timestamp_sec: float
          - pil_image: PIL.Image
          - is_scene_change: bool
          - thumb_path: str
        """
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            step_frames = max(1, int(fps * self.sample_interval_sec))

            prev_gray_small = None
            frame_idx = 0

            while frame_idx < total_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                success, frame = cap.read()
                if not success or frame is None:
                    break

                timestamp_sec = round(frame_idx / fps, 2)

                # Scene change detection using downscaled grayscale image for speed
                small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
                gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

                is_scene_change = False
                if prev_gray_small is not None:
                    # Normalized absolute difference
                    diff = cv2.absdiff(gray_small, prev_gray_small)
                    non_zero_ratio = np.mean(diff) / 255.0
                    # Skip visually identical consecutive frames to avoid redundant OCR & thumbnail I/O
                    if non_zero_ratio < 0.003:
                        frame_idx += step_frames
                        continue
                    if non_zero_ratio > self.scene_change_thresh:
                        is_scene_change = True
                else:
                    is_scene_change = True

                prev_gray_small = gray_small

                # Save keyframe preview thumbnail
                thumb_name = f"frame_{record_id}_{frame_idx}.jpg"
                thumb_path = os.path.join(THUMBNAIL_DIR, thumb_name)

                # Save thumbnail
                h, w = frame.shape[:2]
                thumb_w = 320
                thumb_h = int(h * (thumb_w / float(w)))
                resized_thumb = cv2.resize(frame, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
                cv2.imwrite(thumb_path, resized_thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 75])

                # Convert BGR to RGB PIL Image for OCR
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_frame)

                yield {
                    "record_id": record_id,
                    "frame_idx": frame_idx,
                    "timestamp_sec": timestamp_sec,
                    "pil_image": pil_image,
                    "is_scene_change": is_scene_change,
                    "thumb_path": thumb_path
                }

                frame_idx += step_frames
        finally:
            cap.release()
