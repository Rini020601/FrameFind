"""
Smart Auto-Naming Module for Screenrecord Manager
Uses Visual Salience, Ground-Truth macOS Menu Bar Detection, URL Parsing,
and Domain Context to accurately name screen recordings after the TRUE central content
(e.g., 'GitHub - Email Settings', 'Apple Maps - McDonald\'s', 'Google Search - How To Screen Record On Mac')
instead of generic button labels or peripheral bookmarks.
"""

import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import unquote_plus

UI_STOPWORDS = {
    # Browser peripheral UI & buttons
    "translate", "new tab", "search google or type url", "bookmarks", "bookmark",
    "extensions", "sign in", "sign up", "login", "register", "share", "clear",
    "history", "downloads", "settings", "profile", "password", "incognito",
    "cookies", "accept", "dismiss", "reload", "back", "forward", "home",
    "watch grey's anat...", "clever ai humaniz...", "german a", "python ma",
    "click to stop screen recording", "click o to stop screen recording",
    "relaunch to update", "exercism", "sign in to consula...", "visa",
    "sunrise planner", "adding an email address",

    # macOS window & menu bar noise
    "file", "edit", "view", "window", "help", "favourites", "recents",
    "desktop", "documents", "downloads", "icloud",
    "icloud drive", "shared", "tags", "all tags", "all tags...", "red",
    "orange", "yellow", "green", "blue", "purple", "grey", "dock",
    "apple maps notifications", "notifications may include alerts",

    # Own app UI tokens (prevent self-referential renaming)
    "screenrecord manager", "auto-rename", "library stats", "watcher: desktop active",
    "all captures", "search any text", "jump to timestamp", "privacy redactor"
}

KNOWN_MACOS_APPS = {
    "Chrome": "Google Chrome",
    "Google Chrome": "Google Chrome",
    "Safari": "Safari",
    "Code": "VS Code",
    "Visual Studio Code": "VS Code",
    "Maps": "Apple Maps",
    "Apple Maps": "Apple Maps",
    "Finder": "Finder",
    "Terminal": "Terminal",
    "iTerm": "Terminal",
    "Xcode": "Xcode",
    "Notes": "Notes",
    "Music": "Music",
    "Keynote": "Keynote",
    "Pages": "Pages",
    "Spotify": "Spotify",
    "Slack": "Slack",
    "Discord": "Discord",
    "Zoom": "Zoom"
}


class SmartNamer:
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Strip illegal filesystem characters and collapse whitespace."""
        clean = re.sub(r'[\\/*?:"<>|]', '', name)
        clean = re.sub(r'^[Qq🔍]\s+', '', clean)  # Strip search icon OCR artifact
        clean = re.sub(r'\s+', ' ', clean).strip()
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
        Synthesizes an accurate title representing the MAIN screen context.
        """
        combined = "\n".join(all_ocr_text) if isinstance(all_ocr_text, list) else str(all_ocr_text)
        events_list = events or []

        # -------------------------------------------------------------
        # 1. GROUND-TRUTH MACOS APPLICATION DETECTION
        # The top-left corner of macOS menu bar (x < 0.08, y < 0.035) has the exact app name
        # -------------------------------------------------------------
        detected_app = None
        for e in events_list:
            for b in e.get("bounding_boxes", []):
                box = b.get("box", [1, 1, 0, 0])
                if box[0] < 0.08 and box[1] < 0.035:
                    token = b.get("text", "").strip()
                    if token in KNOWN_MACOS_APPS:
                        detected_app = KNOWN_MACOS_APPS[token]
                        break
            if detected_app:
                break

        if detected_app:
            app_name = detected_app

        subject = None

        # -------------------------------------------------------------
        # 2. URL & WEBSITE CONTEXT (GitHub, Google Search, etc.)
        # -------------------------------------------------------------
        url_match = re.search(r'([a-zA-Z0-9.-]+\.(?:com|org|io|net|edu|app|ai|dev|de))(/[\w/.-]*)?', combined)
        if url_match:
            domain = url_match.group(1).lower().replace("www.", "")
            path = url_match.group(2) or ""

            # A. GitHub Detection
            if "github.com" in domain:
                app_name = "GitHub"
                if "settings/emails" in path or "emails" in path:
                    subject = "Email Settings"
                elif "settings" in path:
                    subject = "Settings"
                else:
                    parts = [p for p in path.split("/") if p]
                    if len(parts) >= 2:
                        subject = f"{parts[0]}/{parts[1]}"
                    elif len(parts) == 1:
                        subject = parts[0]
                    else:
                        subject = "Dashboard"

            # B. Google Search Query
            elif "google.com" in domain and "search?q=" in combined:
                q_match = re.search(r'search\?q=([a-zA-Z0-9+_%-]+)', combined)
                if q_match:
                    raw_q = unquote_plus(q_match.group(1).replace('+', ' '))
                    clean_q = re.sub(r'[^a-zA-Z0-9 ]', '', raw_q).strip().title()
                    if len(clean_q) > 3:
                        subject = clean_q
                        app_name = "Google Search"

        # -------------------------------------------------------------
        # 3. APPLE MAPS DESTINATION / SEARCH QUERY
        # -------------------------------------------------------------
        if not subject and (app_name == "Apple Maps" or "Apple Maps" in combined or "Stadtbezirk" in combined):
            app_name = "Apple Maps"
            # Look for searched place name (e.g., McDonald's, Central Park, etc.)
            maps_match = re.search(r'(?:Q\s+|Search\s+)?([A-Za-z0-9\'\- ]{3,35})\s*\n+(?:Search Nearby|\d+\.?\d*\s*km)', combined)
            if maps_match:
                q = maps_match.group(1).strip()
                q = re.sub(r'^[Qq🔍]\s*', '', q).strip()
                if q and q.lower() not in ["apple maps", "search"]:
                    subject = q
            if not subject:
                # Look for city or street header
                loc_match = re.search(r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s*•\s*\d', combined)
                if loc_match:
                    subject = loc_match.group(1)
                else:
                    subject = "Maps View"

        # -------------------------------------------------------------
        # 4. FINDER FOLDERS
        # -------------------------------------------------------------
        if not subject and (app_name == "Finder" or "Favourites" in combined and "Recents" in combined):
            app_name = "Finder"
            for folder in ["Applications", "Documents", "Downloads", "Desktop", "Movies", "Pictures"]:
                if re.search(rf'\b{folder}\b', combined):
                    subject = folder
                    break
            if not subject:
                subject = "Files"

        # -------------------------------------------------------------
        # 5. CODE EDITORS / TERMINAL: Actual File or Error
        # -------------------------------------------------------------
        if not subject and (app_name in ["VS Code", "Terminal", "Xcode"] or category == "Code & Terminal"):
            # Only consider Code Error if not in Screenrecord Manager UI
            if "Screenrecord Manager" not in combined:
                err_match = re.search(r'\b(TypeError|SyntaxError|NameError|IndexError|ValueError|AttributeError|KeyError)\b', combined)
                if err_match:
                    subject = f"{err_match.group(1)} Fix" if "fix" in combined.lower() else f"{err_match.group(1)} Bug"

            if not subject:
                file_match = re.search(r'\b([a-zA-Z0-9_-]+\.(?:py|pl|ts|tsx|js|jsx|html|css|cpp|rs|go|swift|java))\b', combined)
                if file_match:
                    subject = file_match.group(1)

        # -------------------------------------------------------------
        # 6. VISUAL SALIENCE: Central Headings & Active Content
        # -------------------------------------------------------------
        if not subject and events_list:
            subject = cls._extract_visually_salient_subject(events_list)

        # -------------------------------------------------------------
        # 7. FINAL FALLBACK: Substantive Line
        # -------------------------------------------------------------
        if not subject:
            for text_chunk in all_ocr_text:
                for line in text_chunk.split("\n"):
                    clean_line = line.strip()
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
        """Scores candidate text based on font size, centrality, and substance."""
        candidates: Dict[str, float] = {}

        for e in events:
            boxes = e.get("bounding_boxes", [])
            for b in boxes:
                raw_text = b.get("text", "").strip()
                t_lower = raw_text.lower()

                if len(raw_text) < 3 or t_lower in UI_STOPWORDS or any(s in t_lower for s in ["screenrecord manager", "click to stop"]):
                    continue

                box = b.get("box", [0, 0, 0, 0])
                norm_x, norm_y, norm_w, norm_h = box

                # Reject top menu bar, bottom dock, narrow left sidebar
                if norm_y < 0.055 or norm_y > 0.94:
                    continue
                if norm_x < 0.11 and norm_w < 0.12:
                    continue
                if norm_h < 0.016:
                    continue

                center_x = norm_x + norm_w / 2.0
                center_y = norm_y + norm_h / 2.0
                dist_from_center = ((center_x - 0.5) ** 2 + (center_y - 0.5) ** 2) ** 0.5
                centrality = max(0.2, 1.0 - dist_from_center)

                word_count = len(raw_text.split())
                word_bonus = 1.8 if 2 <= word_count <= 6 else (0.8 if word_count == 1 else 1.0)

                score = (norm_h * 100.0) * centrality * word_bonus
                candidates[raw_text] = candidates.get(raw_text, 0.0) + score

        if not candidates:
            return None

        sorted_cands = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        return sorted_cands[0][0]

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

        counter = 1
        while os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(old_path):
            new_name = f"{safe_title} ({counter}){ext}"
            new_path = os.path.join(parent_dir, new_name)
            counter += 1

        if os.path.abspath(new_path) != os.path.abspath(old_path):
            os.rename(old_path, new_path)

        return new_path
