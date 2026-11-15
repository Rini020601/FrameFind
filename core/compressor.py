"""
Hardware-Accelerated Compressor Module for Screenrecord Manager
Compresses bloated macOS screen recordings (.mov) into optimized .mp4
using Apple VideoToolbox (h264_videotoolbox / hevc_videotoolbox) or OpenCV.
"""

import os
import shutil
import subprocess
import cv2
import time
from typing import Dict, Any, Optional


class VideoCompressor:
    @staticmethod
    def is_ffmpeg_available() -> bool:
        return shutil.which("ffmpeg") is not None

    @classmethod
    def compress_video(
        cls,
        input_path: str,
        output_path: Optional[str] = None,
        target_bitrate_kbps: int = 2500,
        crf: int = 24
    ) -> Dict[str, Any]:
        """
        Compresses input video file.
        Uses Apple VideoToolbox if ffmpeg is available, or falls back to OpenCV re-encoding.
        Returns:
            Dict with original_size, compressed_size, saved_bytes, saved_percent, elapsed_sec, output_path
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        orig_size = os.path.getsize(input_path)
        base_name, _ = os.path.splitext(input_path)

        if not output_path:
            output_path = f"{base_name}_compressed.mp4"

        start_time = time.time()

        if cls.is_ffmpeg_available():
            # Apple VideoToolbox hardware accelerated compression
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-c:v", "h264_videotoolbox",
                "-b:v", f"{target_bitrate_kbps}k",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                output_path
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError:
                # Fallback to libx264 if videotoolbox fails
                cmd_fallback = [
                    "ffmpeg", "-y", "-i", input_path,
                    "-c:v", "libx264", "-crf", str(crf),
                    "-preset", "faster",
                    "-c:a", "aac", "-b:a", "128k",
                    output_path
                ]
                subprocess.run(cmd_fallback, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            # OpenCV Fallback re-encoder
            cls._opencv_compress(input_path, output_path)

        elapsed = round(time.time() - start_time, 2)
        compressed_size = os.path.getsize(output_path) if os.path.exists(output_path) else orig_size
        saved_bytes = max(0, orig_size - compressed_size)
        saved_percent = round((saved_bytes / orig_size) * 100, 1) if orig_size > 0 else 0.0

        return {
            "input_path": input_path,
            "output_path": output_path,
            "orig_size_bytes": orig_size,
            "compressed_size_bytes": compressed_size,
            "saved_bytes": saved_bytes,
            "saved_percent": saved_percent,
            "elapsed_sec": elapsed
        }

    @staticmethod
    def _opencv_compress(input_path: str, output_path: str):
        """Pure Python/OpenCV video re-encoder (no ffmpeg CLI dependency required)."""
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video for compression: {input_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Downscale 4K/Retina recordings to 1080p for massive size savings if width > 1920
        if w > 1920:
            scale = 1920.0 / w
            out_w = 1920
            out_h = int(h * scale)
            # Ensure even dimensions
            out_w = out_w if out_w % 2 == 0 else out_w - 1
            out_h = out_h if out_h % 2 == 0 else out_h - 1
        else:
            out_w, out_h = w, h

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            if (out_w, out_h) != (w, h):
                frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
            out.write(frame)

        cap.release()
        out.release()
