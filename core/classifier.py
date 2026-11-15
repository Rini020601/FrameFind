"""
Classifier Module for Screenrecord Manager
Automatically categorizes captures into domains (Code, Presentation, Meeting, Docs)
and extracts contextual app cues.
"""

import re
from typing import Dict, Any, Tuple

CODE_KEYWORDS = {
    "def ", "class ", "import ", "from ", "return ", "function", "const ", "let ",
    "var ", "public ", "private ", "void ", "int ", "std::", "cout", "printf",
    "traceback", "typeerror", "syntaxerror", "exception", "error:", "npm", "git",
    "docker", "kubectl", "bash", "zsh", "sudo", "curl", "ssh", "pip install",
    "console.log", "async ", "await ", "lambda", "self.", "fn main", "struct"
}

SLIDE_KEYWORDS = {
    "agenda", "overview", "roadmap", "key takeaways", "conclusion",
    "architecture diagram", "q1", "q2", "q3", "q4", "presentation",
    "executive summary", "strategy", "deliverables", "milestone"
}

MEETING_KEYWORDS = {
    "zoom", "google meet", "microsoft teams", "slack", "discord",
    "unmute", "mute", "participants", "screen share", "chat",
    "leave meeting", "record meeting", "raise hand"
}

APP_SIGNATURES = [
    (r"(?i)\b(visual studio code|vs code|code)\b", "VS Code"),
    (r"(?i)\b(terminal|iterm|zsh|bash)\b", "Terminal"),
    (r"(?i)\b(xcode)\b", "Xcode"),
    (r"(?i)\b(google chrome|chrome)\b", "Google Chrome"),
    (r"(?i)\b(safari)\b", "Safari"),
    (r"(?i)\b(slack)\b", "Slack"),
    (r"(?i)\b(zoom\.us|zoom)\b", "Zoom"),
    (r"(?i)\b(figma)\b", "Figma"),
    (r"(?i)\b(notion)\b", "Notion"),
    (r"(?i)\b(postman)\b", "Postman"),
    (r"(?i)\b(pycharm|intellij|webstorm)\b", "JetBrains IDE"),
    (r"(?i)\b(keynote|powerpoint|slides)\b", "Slides"),
]


class CaptureClassifier:
    @staticmethod
    def classify_text(text: str) -> Tuple[str, str]:
        """
        Classify text content into (Category, Inferred App Name).
        Categories: 'Code & Terminal', 'Slides & Presentation', 'Meeting & Chat', 'Doc & Web', 'General'
        """
        text_lower = text.lower()
        
        # 1. Detect App
        inferred_app = "macOS"
        for pattern, app_name in APP_SIGNATURES:
            if re.search(pattern, text):
                inferred_app = app_name
                break

        # 2. Score Categories
        code_score = sum(1 for kw in CODE_KEYWORDS if kw in text_lower)
        slide_score = sum(1 for kw in SLIDE_KEYWORDS if kw in text_lower)
        meeting_score = sum(1 for kw in MEETING_KEYWORDS if kw in text_lower)

        # Detect code-like patterns (indented syntax, brackets, camelCase, snake_case)
        code_symbols = len(re.findall(r"[{}\[\]();=><]", text))
        if code_symbols > 15:
            code_score += 3

        if code_score >= 3 or (inferred_app in ["VS Code", "Terminal", "Xcode", "JetBrains IDE", "Postman"]):
            category = "Code & Terminal"
        elif slide_score >= 2 or inferred_app == "Slides":
            category = "Slides & Presentation"
        elif meeting_score >= 2 or inferred_app in ["Zoom", "Slack"]:
            category = "Meeting & Chat"
        elif len(text.split()) > 40:
            category = "Doc & Web"
        else:
            category = "General"

        return category, inferred_app
