"""
Smart Auto-Naming Module for Screenrecord Manager
Analyzes OCR text, window context, errors, and headings to generate human-readable,
content-aware filenames (e.g., 'VS Code - Pricing Plans TypeError Fix (2026-11-15).mp4')
instead of generic macOS 'Screen Recording 2026-11-15 at 16.30.12.mov'.
"""

import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime


class SmartNamer:
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Strip illegal filesystem characters and collapse whitespace."""
        clean = re.sub(r'[\\/*?:"<>|]', '', name)
        clean = re.sub(r'\s+', ' ', clean).strip()
        # Truncate length if excessively long
        return clean[:75] if len(clean) > 75 else clean

    @classmethod
    def generate_title(
        cls,
        all_ocr_text: List[str],
        app_name: str = "macOS",
        category: str = "General",
        original_path: str = ""
    ) -> str:
        """
        Generate a concise, human-readable title from extracted OCR text.
        """
        combined = "\n".join(all_ocr_text)

        subject = None

        # 1. Look for explicit Code Errors
        error_match = re.search(
            r'\b(TypeError|SyntaxError|NameError|IndexError|ValueError|AttributeError|KeyError|Exception|Error \d+|404 Not Found|500 Server Error)\b.*',
            combined,
            re.IGNORECASE
        )
        if error_match:
            err_line = error_match.group(0).strip()
            # Clean up error line
            err_line = re.split(r'[:\(\n]', err_line)[0].strip()
            # Extract error name + next token
            subject = f"{err_line} Bug"

        # 2. Look for Code Function / Class / File signatures
        if not subject and category == "Code & Terminal":
            code_match = re.search(
                r'\b(?:def|class|function|const|let)\s+([a-zA-Z0-9_]+)',
                combined
            )
            file_match = re.search(
                r'\b([a-zA-Z0-9_-]+\.(?:py|ts|tsx|js|jsx|html|css|cpp|rs|go|swift|java))\b',
                combined
            )

            file_str = file_match.group(1) if file_match else ""
            code_str = code_match.group(1) if code_match else ""

            if file_str and code_str:
                subject = f"{file_str} - {code_str}"
            elif file_str:
                subject = file_str
            elif code_str:
                subject = code_str

        # 3. Look for Slide / Presentation titles
        if not subject and category == "Slides & Presentation":
            slide_match = re.search(
                r'(?i)\b(overview|roadmap|strategy|architecture|key takeaways|summary|quarterly review|q[1-4]|deliverables)\b[^\n]*',
                combined
            )
            if slide_match:
                subject = slide_match.group(0).strip().title()

        # 4. Look for Meeting titles
        if not subject and category == "Meeting & Chat":
            meet_match = re.search(
                r'(?i)\b(daily standup|sprint planning|sync|demo|review|interview|meeting)\b[^\n]*',
                combined
            )
            if meet_match:
                subject = meet_match.group(0).strip().title()

        # 5. Fallback: Extract the most prominent non-trivial heading / first line
        if not subject:
            for text_chunk in all_ocr_text:
                for line in text_chunk.split("\n"):
                    clean_line = line.strip()
                    # Skip common short headers or UI noise
                    if len(clean_line) > 6 and not any(w in clean_line.lower() for w in ["screen recording", "file", "edit", "window", "help", "view"]):
                        subject = clean_line[:40].strip()
                        break
                if subject:
                    break

        if not subject:
            subject = "Screen Capture"

        # Extract date from original file name if available (e.g. 2026-11-15)
        date_match = re.search(r'\d{4}-\d{2}-\d{2}', original_path)
        date_str = date_match.group(0) if date_match else datetime.now().strftime("%Y-%m-%d")

        # Compose final title: "<App> - <Subject> (<Date>)"
        if app_name and app_name != "macOS":
            full_title = f"{app_name} - {subject} ({date_str})"
        else:
            full_title = f"{subject} ({date_str})"

        return cls.sanitize_filename(full_title)

    @classmethod
    def rename_recording_file(cls, old_path: str, new_title: str) -> str:
        """
        Rename file on disk while keeping extension, avoiding collisions.
        Returns the new absolute file path.
        """
        if not os.path.exists(old_path):
            raise FileNotFoundError(f"File not found: {old_path}")

        parent_dir = os.path.dirname(old_path)
        ext = os.path.splitext(old_path)[1]

        safe_title = cls.sanitize_filename(new_title)
        new_name = f"{safe_title}{ext}"
        new_path = os.path.join(parent_dir, new_name)

        # Handle collisions if file already exists
        counter = 1
        while os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(old_path):
            new_name = f"{safe_title} ({counter}){ext}"
            new_path = os.path.join(parent_dir, new_name)
            counter += 1

        if os.path.abspath(new_path) != os.path.abspath(old_path):
            os.rename(old_path, new_path)

        return new_path
