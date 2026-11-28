"""
Local Audio Transcription Module for FrameFind
Extracts audio tracks from screen recordings and transcribes speech locally
using mlx-whisper (Apple Silicon) or openai-whisper when installed.
Aligns spoken segments to timestamped events so spoken words are searchable in FTS5.
"""

import os
import shutil
import logging
import tempfile
import subprocess
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _detect_whisper_backend() -> Optional[str]:
    try:
        import mlx_whisper  # noqa: F401
        return "mlx_whisper"
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return "whisper"
    except ImportError:
        pass
    return None


class AudioTranscriber:
    def __init__(self, model_name: str = "mlx-community/whisper-tiny"):
        self.model_name = model_name
        self.backend = _detect_whisper_backend()
        self._whisper_model = None

    def is_available(self) -> bool:
        return self.backend is not None and shutil.which("ffmpeg") is not None

    def transcribe_video(self, video_path: str) -> List[Dict[str, Any]]:
        """
        Extract audio from a video file and return timestamped speech segments:
        [{"start": float, "end": float, "text": str}, ...]
        Returns [] cleanly if no backend, no ffmpeg, or no audio track exists.
        """
        if not self.is_available() or not os.path.exists(video_path):
            return []

        tmp_wav = None
        try:
            fd, tmp_wav = tempfile.mkstemp(suffix=".wav", prefix="framefind_audio_")
            os.close(fd)

            extract_cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-ac", "1", "-ar", "16000",
                "-f", "wav", tmp_wav,
            ]
            res = subprocess.run(extract_cmd, capture_output=True, check=False, timeout=60)
            if res.returncode != 0 or not os.path.exists(tmp_wav) or os.path.getsize(tmp_wav) < 1024:
                return []

            if self.backend == "mlx_whisper":
                import mlx_whisper
                result = mlx_whisper.transcribe(tmp_wav, path_or_hf_repo=self.model_name)
            elif self.backend == "whisper":
                import whisper
                if self._whisper_model is None:
                    self._whisper_model = whisper.load_model("tiny")
                result = self._whisper_model.transcribe(tmp_wav)
            else:
                return []

            segments = []
            for seg in result.get("segments", []):
                text = (seg.get("text") or "").strip()
                if text:
                    segments.append({
                        "start": round(float(seg.get("start", 0.0)), 2),
                        "end": round(float(seg.get("end", 0.0)), 2),
                        "text": text,
                    })
            return segments
        except Exception as e:
            logger.debug(f"Audio transcription skipped for {video_path}: {e}")
            return []
        finally:
            if tmp_wav and os.path.exists(tmp_wav):
                try:
                    os.unlink(tmp_wav)
                except OSError:
                    pass

    @staticmethod
    def align_transcript_to_events(
        segments: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        record_id: int,
        max_gap_sec: float = 3.0,
    ) -> List[Dict[str, Any]]:
        """
        Attach spoken transcript segments to the nearest timestamped event, or
        create audio-only events if no keyframe is within max_gap_sec.
        """
        if not segments:
            return events

        aligned = list(events)
        for seg in segments:
            seg_text = (seg.get("text") or "").strip()
            if not seg_text:
                continue
            seg_start = float(seg.get("start", 0.0))

            nearest_ev = None
            nearest_dist = float("inf")
            for ev in aligned:
                dist = abs(float(ev.get("timestamp_sec", 0.0)) - seg_start)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_ev = ev

            if nearest_ev is not None and nearest_dist <= max_gap_sec:
                existing = (nearest_ev.get("audio_text") or "").strip()
                nearest_ev["audio_text"] = f"{existing} {seg_text}".strip() if existing else seg_text
            else:
                aligned.append({
                    "record_id": record_id,
                    "timestamp_sec": round(seg_start, 2),
                    "frame_idx": 0,
                    "ocr_text": "",
                    "audio_text": seg_text,
                    "bounding_boxes": [],
                    "is_keyframe": 0,
                    "frame_thumb_path": "",
                })

        aligned.sort(key=lambda e: float(e.get("timestamp_sec", 0.0)))
        return aligned
