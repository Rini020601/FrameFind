"""
Smart Auto-Naming Module for Screenrecord Manager
Uses visual salience, bounding-box geometry, font-size hierarchy, and semantic context
to extract the TRUE primary focus of a screen recording (e.g., 'Web - How To Screen Record On Mac')
while completely ignoring peripheral noise, bookmarks, sidebars, and tiny UI buttons like 'translate'.
"""

import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import unquote_plus

# Stopwords & peripheral UI noise that should NEVER become a recording title
UI_STOPWORDS = {
    # Browser peripheral UI & buttons
    "translate", "new tab", "search google or type url", "bookmarks", "bookmark",
    "extensions", "sign in", "sign up", "login", "register", "share", "clear",
    "history", "downloads", "settings", "profile", "password", "incognito",
    "cookies", "accept", "dismiss", "reload", "back", "forward", "home",
    "watch grey's anat...", "clever ai humaniz...", "german a", "python ma",
    "click to stop screen recording", "click o to stop screen recording",

    # macOS window & menu bar noise
    "file", "edit", "view", "window", "help", "favourites", "recents",
    "applications", "desktop", "documents", "downloads", "icloud",
    "icloud drive", "shared", "tags", "all tags", "all tags...", "red",
    "orange", "yellow", "green", "blue", "purple", "grey", "dock",

    # Own app UI tokens (so Screenrecord Manager previewing a clip doesn't rename itself)
    "screenrecord manager", "auto-rename", "library stats", "watcher: desktop active",
    "all captures", "search any text", "jump to timestamp", "privacy redactor"
}


class SmartNamer:
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Strip illegal filesystem characters and collapse whitespace."""
        clean = re.sub(r'[\\/*?:"<>|]', '', name)
        clean = re.sub(r'\s+', ' ', clean).strip()
        # Truncate length to avoid OS limits
        return clean[:70] if len(clean) > 70 else clean

    @classmethod
    def generate_title(
        cls,
        all_ocr_text: List[str],
        app_name: str = "macOS",
        category: str = "General",
        original_path: str = "",
        events: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Synthesizes a clean, human-readable title based on the PRIMARY screen content.
        Uses geometry, font-size prominence, search URLs, and domain context.
        """
        combined = "\n".join(all_ocr_text) if isinstance(all_ocr_text, list) else str(all_ocr_text)

        subject = None

        # -------------------------------------------------------------
        # 1. WEB SEARCH QUERY DETECTION (e.g. Google, DuckDuckGo, Bing)
        # -------------------------------------------------------------
        search_match = re.search(r'search\?q=([a-zA-Z0-9+_%-]+)', combined)
        if search_match:
            raw_query = unquote_plus(search_match.group(1).replace('+', ' '))
            clean_q = re.sub(r'[^a-zA-Z0-9 ]', '', raw_query).strip().title()
            if len(clean_q) > 4:
                subject = clean_q
                if app_name in ["Google Chrome", "Safari", "macOS"]:
                    app_name = "Web"

        # -------------------------------------------------------------
        # 2. RUNTIME CODE ERRORS & TERMINAL FAILURES
        # Only if in genuine Code/Terminal context (not inside our own manager UI)
        # -------------------------------------------------------------
        if not subject and category == "Code & Terminal":
            # Exclude our own app's preview text
            if "Screenrecord Manager" not in combined:
                error_match = re.search(
                    r'\b(TypeError|SyntaxError|NameError|IndexError|ValueError|AttributeError|KeyError|NullPointerException|404 Not Found|500 Server Error)\b',
                    combined,
                    re.IGNORECASE
                )
                if error_match:
                    err_name = error_match.group(1).strip()
                    subject = f"{err_name} Fix" if "fix" in combined.lower() else f"{err_name} Bug"

        # -------------------------------------------------------------
        # 3. CODE FILE & FUNCTION SIGNATURES (e.g. RINI-RAVINDRAN.pl)
        # -------------------------------------------------------------
        if not subject and category == "Code & Terminal":
            file_match = re.search(
                r'\b([a-zA-Z0-9_-]+\.(?:py|pl|ts|tsx|js|jsx|html|css|cpp|rs|go|swift|java))\b',
                combined
            )
            code_func = re.search(
                r'\b(?:def|class|function)\s+([a-zA-Z0-9_]{3,30})',
                combined
            )
            if file_match and code_func:
                subject = f"{file_match.group(1)} - {code_func.group(1)}"
            elif file_match:
                subject = file_match.group(1)
            elif code_func:
                subject = code_func.group(1)

        # -------------------------------------------------------------
        # 4. VISUAL SALIENCE: Largest / Most Central Text Blocks
        # -------------------------------------------------------------
        if not subject and events:
            subject = cls._extract_visually_salient_subject(events)

        # -------------------------------------------------------------
        # 5. FINDER WINDOW TITLES (e.g. Applications, Documents)
        # -------------------------------------------------------------
        if not subject:
            finder_match = re.search(r'\b(Applications|Documents|Downloads|Desktop|Movies|Pictures)\b', combined)
            if finder_match:
                subject = finder_match.group(1)
                app_name = "Finder"

        # -------------------------------------------------------------
        # 6. SLIDES & PRESENTATION HEADINGS
        # -------------------------------------------------------------
        if not subject and category == "Slides & Presentation":
            slide_match = re.search(
                r'(?i)\b(overview|roadmap|strategy|architecture|key takeaways|summary|quarterly review|milestones)\b[^\n]*',
                combined
            )
            if slide_match:
                subject = slide_match.group(0).strip().title()

        # -------------------------------------------------------------
        # 7. FINAL FALLBACK: Substantive Central Phrase
        # -------------------------------------------------------------
        if not subject:
            for text_chunk in all_ocr_text:
                for line in text_chunk.split("\n"):
                    clean_line = line.strip()
                    # Filter out short or stopword lines
                    if len(clean_line.split()) >= 2 and not any(w in clean_line.lower() for w in UI_STOPWORDS):
                        subject = clean_line[:40].strip()
                        break
                if subject:
                    break

        if not subject:
            subject = "Screen Recording"

        # Extract capture date
        date_match = re.search(r'\d{4}-\d{2}-\d{2}', original_path)
        date_str = date_match.group(0) if date_match else datetime.now().strftime("%Y-%m-%d")

        # Format: "<App> - <Subject> (<Date>)"
        if app_name and app_name not in ["macOS", "Unknown"] and not subject.startswith(app_name):
            full_title = f"{app_name} - {subject} ({date_str})"
        else:
            full_title = f"{subject} ({date_str})"

        return cls.sanitize_filename(full_title)

    @classmethod
    def _extract_visually_salient_subject(cls, events: List[Dict[str, Any]]) -> Optional[str]:
        """
        Scores text elements across all keyframes based on:
          - Font size (bounding box height)
          - Centrality (distance from screen center)
          - Frame persistence (how many frames it stayed visible)
        Filters out peripheral navigation, sidebars, and tiny button labels.
        """
        candidates: Dict[str, float] = {}

        for e in events:
            boxes = e.get("bounding_boxes", [])
            for b in boxes:
                raw_text = b.get("text", "").strip()
                t_lower = raw_text.lower()

                # Filter stopwords & short symbols
                if len(raw_text) < 3 or t_lower in UI_STOPWORDS or any(s in t_lower for s in ["screenrecord manager", "click to stop"]):
                    continue

                box = b.get("box", [0, 0, 0, 0])
                norm_x, norm_y, norm_w, norm_h = box

                # 1. Reject Top OS/Browser Menu Bar (top 5.5%)
                if norm_y < 0.055:
                    continue

                # 2. Reject Bottom Dock (bottom 6%)
                if norm_y > 0.94:
                    continue

                # 3. Reject Narrow Leftmost Sidebars (x < 11% and width < 12%)
                if norm_x < 0.11 and norm_w < 0.12:
                    continue

                # 4. Reject Micro-text (tiny buttons, icons, timestamps with h < 0.016)
                if norm_h < 0.016:
                    continue

                # Centrality score (closer to center = higher weight)
                center_x = norm_x + norm_w / 2.0
                center_y = norm_y + norm_h / 2.0
                dist_from_center = ((center_x - 0.5) ** 2 + (center_y - 0.5) ** 2) ** 0.5
                centrality = max(0.2, 1.0 - dist_from_center)

                # Heading bonus for multi-word phrases (2-6 words)
                word_count = len(raw_text.split())
                word_bonus = 1.6 if 2 <= word_count <= 6 else (0.8 if word_count == 1 else 1.0)

                # Composite score: Size * Centrality * Substance
                score = (norm_h * 100.0) * centrality * word_bonus
                candidates[raw_text] = candidates.get(raw_text, 0.0) + score

        if not candidates:
            return None

        # Sort by visual salience score
        sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        return sorted_candidates[0][0]

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
