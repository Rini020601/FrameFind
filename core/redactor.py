"""
Privacy & Redaction Module for Screenrecord Manager
Automatically detects sensitive tokens (API keys, emails, passwords, auth tokens)
and applies bounding-box blurring/masking to protect privacy before sharing.
"""

import re
import cv2
import numpy as np
from PIL import Image, ImageFilter
from typing import List, Dict, Any, Tuple

REDACTION_PATTERNS = [
    ("OpenAI / API Key", re.compile(r"\b(sk-[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z-_]{35})\b")),
    ("GitHub Token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Bearer Token", re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{20,}\b")),
    ("Email Address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")),
    ("Private Key Header", re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----")),
    ("Password / Secret Assignment", re.compile(r"(?i)\b(password|secret|token|passwd)\s*[:=]\s*['\"][^'\"]{4,}['\"]"))
]


class PrivacyRedactor:
    @staticmethod
    def detect_secrets(text: str) -> List[Dict[str, str]]:
        """Find sensitive matches in text."""
        findings = []
        for label, pattern in REDACTION_PATTERNS:
            for match in pattern.finditer(text):
                findings.append({
                    "label": label,
                    "value": match.group(0),
                    "start": match.start(),
                    "end": match.end()
                })
        return findings

    @classmethod
    def redact_frame(
        cls,
        image: Image.Image,
        bounding_boxes: List[Dict[str, Any]],
        blur_radius: int = 25
    ) -> Tuple[Image.Image, List[str]]:
        """
        Finds bounding boxes that contain sensitive credentials/emails and blurs those regions.
        Returns:
            (redacted_image, list_of_redaction_messages)
        """
        # Convert PIL to CV2 image (BGR)
        img_np = np.array(image.convert("RGB"))
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        h, w = img_bgr.shape[:2]

        redacted_notes = []

        for item in bounding_boxes:
            box_text = item.get("text", "")
            secrets = cls.detect_secrets(box_text)
            if not secrets:
                continue

            # item["box"] is [norm_x, norm_y, norm_w, norm_h] (top-left origin)
            norm_x, norm_y, norm_w, norm_h = item["box"]
            x1 = max(0, int(norm_x * w) - 4)
            y1 = max(0, int(norm_y * h) - 4)
            x2 = min(w, int((norm_x + norm_w) * w) + 4)
            y2 = min(h, int((norm_y + norm_h) * h) + 4)

            if x2 > x1 and y2 > y1:
                roi = img_bgr[y1:y2, x1:x2]
                # Heavy Gaussian blur over sensitive region
                ksize = max(15, (blur_radius // 2) * 2 + 1)
                blurred_roi = cv2.GaussianBlur(roi, (ksize, ksize), 30)
                img_bgr[y1:y2, x1:x2] = blurred_roi

                # Subtle dark outline & label marker
                cv2.rectangle(img_bgr, (x1, y1), (x2, y2), (40, 40, 40), 1)

                labels = ", ".join(s["label"] for s in secrets)
                redacted_notes.append(f"Redacted {labels}: '{box_text[:12]}...'")

        # Convert back to PIL
        rgb_redacted = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_redacted), redacted_notes
