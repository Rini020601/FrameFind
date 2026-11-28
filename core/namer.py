"""
Smart Auto-Naming Module for FrameFind
Uses Visual Salience, Ground-Truth macOS Menu Bar Detection, URL Parsing,
and Domain Context to accurately name screen recordings after the TRUE central content
(e.g., 'GitHub - Email Settings', 'Apple Maps - McDonald\'s', 'Google Search - How To Screen Record On Mac')
instead of generic button labels or peripheral bookmarks.
"""

import os
import re
from collections import Counter
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import unquote_plus

from core.summariser import FrameSummariser

UI_STOPWORDS = {
    # Browser peripheral UI & buttons
    "translate", "new tab", "search google or type url", "bookmarks", "bookmark",
    "extensions", "sign in", "sign up", "login", "register", "share", "clear",
    "history", "downloads", "settings", "profile", "password", "incognito",
    "cookies", "accept", "dismiss", "reload", "back", "forward", "home",
    "watch grey's anat...", "clever ai humaniz...", "german a", "python ma",
    "click to stop screen recording", "click o to stop screen recording",
    "relaunch to update", "exercism", "sign in to consula...", "visa",
    "adding an email address",
    "what do you want to play", "what do you want to play?",
    "to exit full screen, press and hold", "advertisement",

    # macOS window & menu bar noise
    "file", "edit", "view", "window", "help", "favourites", "recents",
    "desktop", "documents", "downloads", "icloud",
    "icloud drive", "shared", "tags", "all tags", "all tags...", "red",
    "orange", "yellow", "green", "blue", "purple", "grey", "dock",
    "apple maps notifications", "notifications may include alerts",

    # Own app UI tokens (prevent self-referential renaming)
    "framefind", "screenrecord manager", "auto-rename", "library stats", "watcher: desktop active",
    "all captures", "search any text", "jump to timestamp", "privacy redactor",

    # Planner / wellness widget noise
    "highlights of the year", "highlights of the month", "today's quote",
    "today's notes", "mini notepad", "mood", "someday tasks", "wellness",
    "supplements", "gratitude", "habit tracker", "daily planner", "weekly planner",
    "morning routine", "evening routine", "water intake", "sleep tracker",

    # Generic Chrome extension / sidebar noise
    "new chat", "library", "my day", "today", "upcoming", "all tasks",
    "add a task", "try copilot", "my analytics", "pinned", "done", "inbox",
    "search or create", "home", "calendar", "habits", "goals",
}

KNOWN_MACOS_APPS = {
    "Chrome": "Google Chrome",
    "Google Chrome": "Google Chrome",
    "Brave": "Brave Browser",
    "Brave Browser": "Brave Browser",
    "Arc": "Arc",
    "Firefox": "Firefox",
    "Safari": "Safari",
    "Code": "VS Code",
    "Visual Studio Code": "VS Code",
    "Cursor": "Cursor",
    "Antigravity": "Antigravity",
    "Maps": "Apple Maps",
    "Apple Maps": "Apple Maps",
    "Finder": "Finder",
    "Preview": "Preview",
    "Terminal": "Terminal",
    "iTerm": "Terminal",
    "iTerm2": "Terminal",
    "Ghostty": "Ghostty",
    "Warp": "Warp",
    "Xcode": "Xcode",
    "Notes": "Notes",
    "Messages": "Messages",
    "Mail": "Mail",
    "WhatsApp": "WhatsApp",
    "TextEdit": "TextEdit",
    "System Settings": "System Settings",
    "Reminders": "Reminders",
    "Music": "Music",
    "Keynote": "Keynote",
    "Pages": "Pages",
    "Numbers": "Numbers",
    "Microsoft Word": "Microsoft Word",
    "Microsoft Excel": "Microsoft Excel",
    "Microsoft PowerPoint": "Microsoft PowerPoint",
    "Obsidian": "Obsidian",
    "Notion": "Notion",
    "Figma": "Figma",
    "Postman": "Postman",
    "Spotify": "Spotify",
    "Calendar": "Calendar",
    "Photos": "Photos",
    "QuickTime Player": "QuickTime Player",
    "VLC": "VLC",
    "Slack": "Slack",
    "Discord": "Discord",
    "Zoom": "Zoom",
    "zoom.us": "Zoom",
    "ChatGPT": "ChatGPT",
    "Claude": "Claude",
}

BROWSER_APPS = {
    "Google Chrome", "Brave Browser", "Safari", "Arc", "Firefox",
}

KNOWN_SITE_NAMES = {
    "youtube.com": "YouTube",
    "github.com": "GitHub",
    "chatgpt.com": "ChatGPT",
    "claude.ai": "Claude",
    "netflix.com": "Netflix",
    "reddit.com": "Reddit",
    "linkedin.com": "LinkedIn",
    "spotify.com": "Spotify",
    "mail.google.com": "Gmail",
    "gmail.com": "Gmail",
    "docs.google.com": "Google Docs",
    "sheets.google.com": "Google Sheets",
    "drive.google.com": "Google Drive",
    "calendar.google.com": "Google Calendar",
    "google.com": "Google",
    "notion.so": "Notion",
    "figma.com": "Figma",
    "x.com": "X",
    "twitter.com": "X",
    "twitch.tv": "Twitch",
    "stackoverflow.com": "Stack Overflow",
}

MENU_BAR_STOPWORDS = {
    "file", "edit", "view", "history", "bookmarks", "profiles", "tab",
    "window", "help", "go", "tools", "shell", "format", "insert",
    "selection", "run", "terminal", "debug", "navigate", "refactor",
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
        app_frame_counts = Counter()
        for e in events_list:
            apps_in_frame = set()
            for b in e.get("bounding_boxes", []):
                box = b.get("box", [1, 1, 0, 0])
                if box[0] < 0.08 and box[1] < 0.035:
                    token = b.get("text", "").strip()
                    if token in KNOWN_MACOS_APPS:
                        apps_in_frame.add(KNOWN_MACOS_APPS[token])
            app_frame_counts.update(apps_in_frame)

        detected_app = app_frame_counts.most_common(1)[0][0] if app_frame_counts else None

        if not detected_app and events_list:
            # Fallback: first clean app-like label in the top-left macOS menu bar
            menu_candidates = []
            for e in events_list:
                for b in e.get("bounding_boxes", []):
                    box = b.get("box", [1, 1, 0, 0])
                    if 0.015 <= box[0] < 0.095 and box[1] < 0.035:
                        token = b.get("text", "").strip()
                        if (
                            len(token) >= 3
                            and token[0].isalpha()
                            and token.lower() not in MENU_BAR_STOPWORDS
                            and token.lower() not in UI_STOPWORDS
                        ):
                            menu_candidates.append((box[0], token))
            if menu_candidates:
                menu_candidates.sort(key=lambda item: item[0])
                detected_app = menu_candidates[0][1]

        if detected_app:
            app_name = detected_app

        # Fullscreen Spotify hides the macOS menu bar. Its product name and
        # library vocabulary are stronger evidence than generic top-bar text.
        spotify_signals = (
            re.search(r"\bSpotify\b", combined, re.I)
            and any(
                signal in combined.lower()
                for signal in ("your library", "daily mix", "liked songs", "playlists")
            )
        )
        if spotify_signals:
            app_name = "Spotify"

        photos_signals = (
            re.search(r"(?m)^\s*Photos\s*$", combined, re.I)
            and re.search(r"(?m)^\s*Library\s*$", combined, re.I)
            and any(
                signal in combined.lower()
                for signal in ("all photos", "media types", "featured photos")
            )
        )
        if photos_signals:
            app_name = "Photos"

        calendar_match = re.search(
            r"\b(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+(\d{4})\b",
            combined,
            re.I,
        )
        weekday_count = sum(
            1 for day in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
            if re.search(rf"(?m)^\s*{day}\s*$", combined, re.I)
        )
        calendar_context = calendar_match and weekday_count >= 5
        if calendar_context:
            app_name = "Calendar"

        subject = None

        if calendar_context:
            month = calendar_match.group(1).title()
            subject = f"{month} {calendar_match.group(2)}"

        # Capture hierarchy (screenshots and recordings): identify the app first,
        # then pick the largest clearly visible heading/title across frames.
        # On browser home screens (bare domain in address bar), use the site name.
        is_single_screenshot = len(events_list) == 1
        if events_list and not subject and app_name in BROWSER_APPS:
            subject = cls._extract_browser_home_site(events_list)

        uses_special_context = app_name in ("Spotify", "Apple Maps", "Finder")
        if events_list and not subject and not uses_special_context:
            is_youtube_watch = "youtube.com/watch" in combined.lower()
            subject = cls._extract_visually_salient_subject(
                events_list,
                app_name=app_name,
                ignore_right_sidebar=is_youtube_watch,
            )

        # -------------------------------------------------------------
        # 1.5  ACTIVE BROWSER TAB DETECTION (Chrome / Safari tab strip)
        # Chrome draws a horizontal tab strip at y ≈ 0.030–0.075.
        # Active tab = the tab label that does NOT have a trailing close-
        # button "X" (Chrome appends " X" OCR artifact to background tabs).
        # -------------------------------------------------------------
        if not subject and events_list and app_name in ("Google Chrome", "Safari"):
            tab_zone_texts: Dict[str, int] = {}
            bg_tabs: set = set()

            for e in events_list:
                for b in e.get("bounding_boxes", []):
                    x, y, w, h = b.get("box", [0, 0, 0, 0])
                    txt = b.get("text", "").strip()

                    # Must be in tab-strip zone
                    if not (0.028 <= y <= 0.078 and x > 0.09):
                        continue
                    if len(txt) < 4 or h < 0.007:
                        continue
                    # Skip obvious system-clock / single-char favicon artifacts
                    if len(txt) <= 2 or re.match(r'^\d{1,2}:\d{2}', txt):
                        continue
                    # Skip known noise phrases
                    if txt.lower() in UI_STOPWORDS:
                        continue

                    # Background tab: ends with trailing close-button " X"
                    if re.search(r'\s+[Xx×]$', txt):
                        clean = re.sub(r'\s+[Xx×]$', '', txt).strip()
                        bg_tabs.add(clean.lower())
                    else:
                        # Candidate for active tab
                        tab_zone_texts[txt] = tab_zone_texts.get(txt, 0) + 1

            # Active tab candidates are those that never appeared as background
            active_candidates = {
                k: v for k, v in tab_zone_texts.items()
                if k.lower() not in bg_tabs
                and k.lower() not in UI_STOPWORDS
                and not re.match(r'^[\d\s]+$', k)          # reject all-digit strings
                and len(set(k.lower())) > 2                 # reject "000000000"
                and len(k) >= 4
            }

            if active_candidates:
                active_tab = max(active_candidates, key=active_candidates.get)
                subject = active_tab

        # -------------------------------------------------------------
        # 2. URL & WEBSITE CONTEXT (GitHub, Google Search, etc.)
        # -------------------------------------------------------------
        url_match = re.search(r'([a-zA-Z0-9.-]+\.(?:com|org|io|net|edu|app|ai|dev|de))(/[\w/.-]*)?', combined)
        if url_match and not (is_single_screenshot and subject):
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
        # 3. SPOTIFY CONTENT
        # -------------------------------------------------------------
        if not subject and app_name == "Spotify":
            # Prefer the user's current library/collection context. Promotional
            # headings near an "Advertisement" label must never name a capture.
            spotify_headings = (
                "Your Library",
                "Liked Songs",
                "Daily Mix",
            )
            for heading in spotify_headings:
                if re.search(rf"\b{re.escape(heading)}\b", combined, re.I):
                    subject = heading
                    break

            if not subject:
                track_match = re.search(
                    r"^([^\n]{3,60}?)\s+-\s+From\b", combined, re.I | re.M
                )
                if track_match:
                    subject = track_match.group(1).strip()

            if not subject:
                subject = "Music"

        # -------------------------------------------------------------
        # 4. APPLE MAPS DESTINATION / SEARCH QUERY
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
        # 5. FINDER FOLDERS
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
        # 6. CODE EDITORS / TERMINAL: Actual File or Error
        # -------------------------------------------------------------
        if not subject and (app_name in ["VS Code", "Terminal", "Xcode"] or category == "Code & Terminal"):
            # Only consider Code Error if not in FrameFind UI
            if "FrameFind" not in combined and "Screenrecord Manager" not in combined:
                err_match = re.search(r'\b(TypeError|SyntaxError|NameError|IndexError|ValueError|AttributeError|KeyError)\b', combined)
                if err_match:
                    subject = f"{err_match.group(1)} Fix" if "fix" in combined.lower() else f"{err_match.group(1)} Bug"

            if not subject:
                file_match = re.search(r'\b([a-zA-Z0-9_-]+\.(?:py|pl|ts|tsx|js|jsx|html|css|cpp|rs|go|swift|java))\b', combined)
                if file_match:
                    subject = file_match.group(1)

        # -------------------------------------------------------------
        # 7. VISUAL SALIENCE: Central Headings & Active Content
        # -------------------------------------------------------------
        if not subject and events_list:
            subject = cls._extract_visually_salient_subject(events_list, app_name=app_name)

        # -------------------------------------------------------------
        # 8. FINAL FALLBACK: Substantive Line
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

        # Fallback for recordings when no clear heading/title was found above:
        # use the dominant phrase across the majority of sampled frames.
        dominant_context = None
        if len(events_list) >= 2 and (not subject or subject == "Screen Recording"):
            app_words = set(app_name.lower().split()) if app_name else set()
            dominant_context = FrameSummariser.summarise(
                events_list, exclude_words=app_words, max_words=5
            )
            if dominant_context:
                subject = dominant_context
                if detected_app:
                    app_name = detected_app

        frame_summary = None

        # Extract capture date
        date_match = re.search(r'\d{4}-\d{2}-\d{2}', original_path)
        date_str = date_match.group(0) if date_match else datetime.now().strftime("%Y-%m-%d")

        # Keep the date suffix intact by trimming long subjects cleanly at a word boundary
        max_subject_len = max(20, 70 - len(f"{app_name} -  ({date_str})") if app_name and app_name not in ["macOS", "Unknown"] else 70 - len(f" ({date_str})"))
        if len(subject) > max_subject_len:
            trimmed = subject[:max_subject_len].rsplit(" ", 1)[0].strip()
            subject = trimmed if len(trimmed) >= 15 else subject[:max_subject_len].strip()

        # Format: "<App> - <Subject> - <Summary> (<Date>)"
        if app_name and app_name not in ["macOS", "Unknown"] and not subject.startswith(app_name):
            if frame_summary:
                full_title = f"{app_name} - {subject} - {frame_summary} ({date_str})"
            else:
                full_title = f"{app_name} - {subject} ({date_str})"
        else:
            if frame_summary:
                full_title = f"{subject} - {frame_summary} ({date_str})"
            else:
                full_title = f"{subject} ({date_str})"

        return cls.sanitize_filename(full_title)

    @classmethod
    def _extract_browser_home_site(cls, events: List[Dict[str, Any]]) -> Optional[str]:
        """Return the site name when the browser address bar shows a bare home-screen domain."""
        url_pattern = re.compile(
            r'^(?:https?://)?(?:www\.)?([a-zA-Z0-9.-]+\.(?:com|org|io|net|edu|app|ai|dev|de|tv|so|co))(?:/(.*))?$'
        )
        for e in events:
            for b in e.get("bounding_boxes", []):
                box = b.get("box", [0, 0, 0, 0])
                norm_x, norm_y, _, _ = box
                if not (0.070 <= norm_y <= 0.135 and 0.10 <= norm_x <= 0.75):
                    continue
                txt = b.get("text", "").strip()
                m = url_pattern.match(txt)
                if not m:
                    continue
                domain = m.group(1).lower()
                path = (m.group(2) or "").strip("/")
                if path:
                    return None
                if domain in KNOWN_SITE_NAMES:
                    return KNOWN_SITE_NAMES[domain]
                base = domain.split(".")[0]
                return base.title() if base else None
        return None

    @classmethod
    def _extract_visually_salient_subject(
        cls,
        events: List[Dict[str, Any]],
        app_name: Optional[str] = None,
        ignore_right_sidebar: bool = False,
    ) -> Optional[str]:
        """Scores candidate text primarily by heading size (height), then centrality and substance."""
        candidates: Dict[str, float] = {}
        app_lower = app_name.lower() if app_name else ""

        for e in events:
            boxes = e.get("bounding_boxes", [])
            for b in boxes:
                raw_text = b.get("text", "").strip()
                t_lower = raw_text.lower()

                if len(raw_text) < 3 or t_lower in UI_STOPWORDS or any(s in t_lower for s in ["framefind", "screenrecord manager", "click to stop"]):
                    continue
                if app_lower and t_lower == app_lower:
                    continue

                # Reject all-digit strings, low-variety strings, and numeric/unit tokens (e.g. "22 0C")
                if re.match(r'^[\d\s]+$', raw_text):
                    continue
                if len(set(t_lower.replace(' ', ''))) <= 2:
                    continue
                if sum(1 for c in raw_text if c.isalpha()) < 3:
                    continue
                # Reject short UI button/bullet chrome like "+ Create" or "• Duplicates"
                if re.match(r'^[+•\-<>]\s+\S+$', raw_text):
                    continue

                box = b.get("box", [0, 0, 0, 0])
                norm_x, norm_y, norm_w, norm_h = box

                # Reject top menu bar, bottom dock/status bar, narrow left sidebar
                if norm_y < 0.045 or norm_y > 0.90 or (norm_y + norm_h) > 0.94:
                    continue
                if norm_x < 0.11 and norm_w < 0.12:
                    continue
                if ignore_right_sidebar and norm_x >= 0.68 and norm_y >= 0.15:
                    continue
                if norm_h < 0.015:
                    continue

                center_x = norm_x + norm_w / 2.0
                center_y = norm_y + norm_h / 2.0
                dist_from_center = ((center_x - 0.5) ** 2 + (center_y - 0.5) ** 2) ** 0.5
                centrality = max(0.7, 1.0 - 0.3 * dist_from_center)

                word_count = len(raw_text.split())
                word_bonus = 1.25 if 2 <= word_count <= 8 else (0.85 if word_count == 1 else 1.0)

                # Heading height is the primary signal; centrality and word count act as tie-breakers
                score = ((norm_h * 100.0) ** 2) * centrality * word_bonus
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

        safe_title = cls.sanitize_filename(new_title) or "Capture"
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
