"""
Extractive Frame Summariser — Pure Python, zero external model downloads.

Algorithm:
  1. Collect all OCR text from every keyframe event.
  2. Weight each text token by how many *distinct frames* it appeared in
     (frequency across time = salience, not just raw count).
  3. Build scored bigram + trigram candidate phrases from that weighted pool.
  4. Filter stopwords, noise patterns, and already-known context (app name, subject).
  5. Return the top-scoring phrase trimmed to 3–4 words.

Result appended to filenames:
  Google Chrome - Sunrise Planner - Daily Goal Tracker (2026-11-15).mov
  VS Code - TypeError Bug - Null Reference Fix (2026-11-15).mov
"""

import re
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional, Set

# ---------------------------------------------------------------------------
# Stopword set — words that should never appear in a filename summary
# ---------------------------------------------------------------------------
SUMMARY_STOPWORDS: Set[str] = {
    # Articles / determiners
    "the", "a", "an", "this", "that", "these", "those", "my", "your",
    "our", "their", "his", "her", "its", "some", "any", "all", "both",
    "each", "every", "few", "more", "most", "other", "such", "no", "nor",
    # Pronouns
    "i", "you", "he", "she", "we", "they", "it", "me", "him", "us", "them",
    # Prepositions
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "through", "about", "above", "below", "between", "during",
    "after", "before", "over", "under", "out", "off", "up", "down",
    # Conjunctions / auxiliary verbs
    "and", "or", "but", "so", "if", "then", "than", "when", "where",
    "which", "who", "how", "be", "is", "are", "was", "were", "has", "have",
    "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "can", "not", "also", "just", "here", "there",
    # Generic action verbs (too vague for a filename)
    "click", "open", "close", "save", "cancel", "search", "back", "next",
    "done", "go", "get", "set", "use", "see", "make", "take", "give",
    "know", "look", "want", "need", "try", "keep", "let", "put", "run",
    "work", "add", "edit", "delete", "remove", "new", "ok", "yes", "no",
    # Time / date filler
    "am", "pm", "today", "yesterday", "now", "ago", "recently", "first",
    "last", "right", "left", "top", "bottom", "good", "best", "same",
    # macOS / browser UI noise already in namer but repeated for safety
    "menu", "toolbar", "window", "tab", "page", "view", "screen", "button",
    "file", "edit", "help", "settings", "profile", "sign", "login", "home",
    "finder", "output", "terminal", "problems", "outline", "timeline",
    "general", "account", "billing", "security", "notification", "notifications",
    "framefind", "screenrecord", "manager",
}

# Patterns that are definitely noise — never include in summary
_NOISE_PATTERNS = [
    r'^[\d\s]+$',          # pure digits / spaces
    r'^[^a-zA-Z]{1,3}$',  # symbols / very short non-alpha
    r'^\d{1,2}:\d{2}',    # timestamps like "14:30"
    r'^https?://',         # raw URLs
    r'\.(com|org|io|net|app|ai|dev)$',  # bare domains
]


def _is_noise(token: str) -> bool:
    if len(token) < 3:
        return True
    if len(set(token.lower())) <= 2:   # "000000000", "aaa"
        return True
    for pat in _NOISE_PATTERNS:
        if re.search(pat, token, re.I):
            return True
    return False


def _tokenise(text: str) -> List[str]:
    """Split text into clean word tokens."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'_-]{1,30}", text)
    return [t for t in tokens if not _is_noise(t) and t.lower() not in SUMMARY_STOPWORDS]


def _event_segments(event: Dict[str, Any]) -> List[str]:
    """Keep OCR lines separate so phrases never cross unrelated UI regions."""
    boxes = event.get("bounding_boxes", [])
    if boxes:
        segments = []
        for box in boxes:
            text = box.get("text", "").strip()
            if not text:
                continue
            geometry = box.get("box")
            if geometry and len(geometry) == 4:
                x, y, width, _ = geometry
                # Menu bars, docks, and narrow navigation sidebars persist in
                # every frame but describe application chrome, not the work.
                if y < 0.055 or y > 0.93:
                    continue
                if x < 0.18 and width < 0.16:
                    continue
            segments.append(text)
        return segments
    return [line for line in event.get("ocr_text", "").splitlines() if line.strip()]


def _is_chrome_or_command_segment(text: str) -> bool:
    """Reject persistent application chrome, command echoes, and status rows."""
    clean = text.strip()
    lower = clean.lower()
    if re.match(
        r"^[•›>+\-\s]*(ran|edited|show details|ask codex|you approved)\b",
        lower,
    ):
        return True
    if any(marker in lower for marker in ("/bin/", "venv/bin", "~/desktop/")):
        return True
    if re.search(r"\b(?:mon|tue|wed|thu|fri|sat|sun)\b.*\b\d{1,2}:\d{2}\b", lower):
        return True
    return False


def _frame_weighted_token_freq(events: List[Dict[str, Any]]) -> Counter:
    """
    Count how many *distinct frames* each token appears in.
    A token appearing in 8 frames counts more than one seen in 1 frame.
    """
    token_frames: Dict[str, Set[int]] = defaultdict(set)

    for frame_idx, event in enumerate(events):
        for segment in _event_segments(event):
            for token in _tokenise(segment):
                token_frames[token.lower()].add(frame_idx)

    return Counter({tok: len(frames) for tok, frames in token_frames.items()})


def _candidate_phrases(events: List[Dict[str, Any]], _freq: Counter) -> Counter:
    """
    Build scored bigram and trigram candidates from per-frame token sequences.
    Score prioritizes frame coverage, using phrase length only as a tie-breaker.
    """
    phrase_frames: Dict[str, Set[int]] = defaultdict(set)
    phrase_display: Dict[str, str] = {}
    phrase_bonus: Dict[str, int] = defaultdict(int)

    for frame_idx, event in enumerate(events):
        for segment in _event_segments(event):
            if _is_chrome_or_command_segment(segment):
                continue
            tokens = _tokenise(segment)
            title_bonus = 10 if re.search(r"^[^A-Za-z]*[A-Z]", segment) else 0
            # Bigrams
            for i in range(len(tokens) - 1):
                w1, w2 = tokens[i], tokens[i + 1]
                phrase = f"{w1} {w2}"
                key = phrase.lower()
                phrase_frames[key].add(frame_idx)
                phrase_display.setdefault(key, phrase)
                phrase_bonus[key] = max(phrase_bonus[key], title_bonus)

            # Trigrams
            for i in range(len(tokens) - 2):
                w1, w2, w3 = tokens[i], tokens[i + 1], tokens[i + 2]
                phrase = f"{w1} {w2} {w3}"
                key = phrase.lower()
                phrase_frames[key].add(frame_idx)
                phrase_display.setdefault(key, phrase)
                phrase_bonus[key] = max(phrase_bonus[key], title_bonus)

    phrase_scores: Counter = Counter()
    for key, frames in phrase_frames.items():
        display = phrase_display[key]
        word_count = len(display.split())
        phrase_scores[display] = len(frames) * 100 + word_count + phrase_bonus[key]
    return phrase_scores


class FrameSummariser:
    @staticmethod
    def summarise(
        events: List[Dict[str, Any]],
        exclude_words: Optional[Set[str]] = None,
        max_words: int = 4,
    ) -> Optional[str]:
        """
        Returns a 3–4 word extractive summary of the most prominent content
        across all keyframe events, or None if nothing meaningful is found.

        Args:
            events:        List of event dicts (each has bounding_boxes / ocr_text).
            exclude_words: Words already used in app_name / subject — skip them
                           to avoid redundancy like "Chrome - Chrome Tab Overview".
            max_words:     Cap on summary word count (default 4).
        """
        if not events:
            return None

        exclude = {w.lower() for w in (exclude_words or set())}

        # 1. Per-token frame-frequency
        freq = _frame_weighted_token_freq(events)
        if not freq:
            return None

        # 2. Candidate phrases scored by frequency
        phrase_scores = _candidate_phrases(events, freq)

        # 3. Filter phrases containing excluded / low-frequency tokens
        filtered: Counter = Counter()
        required_frames = max(2, len(events) // 2 + 1)
        for phrase, score in phrase_scores.items():
            phrase_lower = phrase.lower()
            tokens = phrase_lower.split()
            # Drop if any word is in the exclude set
            if any(tok in exclude for tok in tokens):
                continue
            # Drop if any word is in stopwords (belt-and-suspenders)
            if any(tok in SUMMARY_STOPWORDS for tok in tokens):
                continue
            # The exact phrase must occur in a strict majority of frames.
            phrase_frame_count = score // 100
            if phrase_frame_count < required_frames:
                continue
            filtered[phrase] = score

        # 4. If no good phrase, fall back to top single tokens
        if not filtered:
            top_tokens = [
                tok for tok, _ in freq.most_common(20)
                if tok not in exclude
                and tok not in SUMMARY_STOPWORDS
                and not _is_noise(tok)
                and freq[tok] >= required_frames
            ]
            if not top_tokens:
                return None
            # Pick up to max_words tokens and title-case them
            summary_tokens = top_tokens[:max_words]
            return " ".join(t.title() for t in summary_tokens)

        # 5. Pick best phrase, trim to max_words
        best_phrase = filtered.most_common(1)[0][0]
        words = best_phrase.split()[:max_words]
        return " ".join(w.title() for w in words)
