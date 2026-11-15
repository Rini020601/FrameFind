# ⚡ Screenrecord Manager

> **Intelligent Screen-Recording & Screenshot Indexer with Native Apple Vision OCR, Jump-to-Timestamp Search, Privacy Redaction, and VideoToolbox Compression for macOS.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![macOS](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon%20%2F%20Intel)-black.svg)](https://apple.com)
[![Apple Vision](https://img.shields.io/badge/OCR-Apple%20Vision%20(Neural%20Engine)-purple.svg)](https://developer.apple.com/documentation/vision)
[![PySide6](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt-green.svg)](https://www.qt.io/)
[![SQLite FTS5](https://img.shields.io/badge/Search-SQLite%20FTS5-orange.svg)](https://www.sqlite.org/fts5.html)

---

## 💡 The Problem

On macOS, recordings sit on the Desktop named `Screen Recording 2026-11-15 at 16.30.12.mov` with **zero searchability** and eat tens of gigabytes on MacBook Air SSDs.

If you recorded a 15-minute lecture or a bug reproduction, finding the exact 5 seconds where an error occurred requires manually dragging the scrub bar across the entire video.

**Screenrecord Manager** solves this:
1. Samples keyframes on intelligent scene changes (window switches, terminal outputs, slide transitions).
2. Extracts on-screen text in milliseconds using **Apple Vision's Neural Engine** (`VNRecognizeTextRequest`).
3. Indexes everything into a high-performance **SQLite FTS5** inverted index.
4. Lets you search any error code or slide title and **jumps straight to the exact second in the video player**.
5. Adds **1-Click Privacy Blurring** (auto-blurs API keys, tokens, and emails before sharing) and **Apple VideoToolbox Hardware Compression** (saving 80–90% disk space).

---

## 🏛 Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│               macOS Filesystem Watcher (watchdog)                      │
│            Monitors ~/Desktop & ~/Movies for .mov / .mp4 / .png        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Video Keyframe & Scene Detector                      │
│   • Sub-frame difference & histogram analysis for scene transitions    │
│   • Periodic 2s sampling fallback for gradual typing/scrolling         │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
                    ▼                                ▼
       ┌────────────────────────┐       ┌────────────────────────┐
       │   Native Apple Vision  │       │ Auto-Context Classifier│
       │  VNRecognizeTextRequest│       │ • Code & Terminal      │
       │ (Top-Left Bounding Box)│       │ • Slides & Presentation│
       └────────────┬───────────┘       │ • Meeting & Chat       │
                    │                   └────────────┬───────────┘
                    └───────────────┬────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       SQLite FTS5 Search Engine                        │
│   • Sub-millisecond keyword retrieval, BM25 ranking, highlighted hits  │
│   • Unified schema: 1-frame Screenshots + Multi-chapter Recordings     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 Native PySide6 Desktop GUI Application                 │
│   • Live search-as-you-type with snippet highlights                    │
│   • Interactive Video Scrubber with chapter markers & Jump-to-Second   │
│   • 1-Click Privacy Redactor (Auto-blurs API keys & Emails)            │
│   • Apple VideoToolbox Hardware Compressor (80–90% storage savings)   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

- **🚀 Native Apple Vision Framework (`pyobjc-framework-Vision`)**:
  - Runs directly on Apple Silicon's Neural Engine.
  - Zero external C-binary dependencies (no Tesseract installation required).
  - Normalizes exact word/line bounding boxes for canvas overlays.

- **⏱ Jump-to-Timestamp Video Player**:
  - Search any keyword (e.g. `TypeError`, `pricing-table`, `kubectl`) to see exact timecode hits.
  - Clicking any search hit seeks the hardware video player to that millisecond.

- **🔒 1-Click Privacy Redactor**:
  - Automatically identifies sensitive credentials:
    - OpenAI / AI API keys (`sk-...`)
    - AWS Access Keys (`AKIA...`)
    - GitHub PATs (`ghp_...`)
    - Bearer tokens & Authorization headers
    - Email addresses & Passwords
  - Renders a Gaussian-blurred preview and allows 1-click export of sanitized frames.

- **🗜 Apple VideoToolbox Hardware Compression**:
  - Uses macOS `h264_videotoolbox` hardware acceleration to compress bloated screen captures into crisp, compact files (e.g., 850 MB $\rightarrow$ 65 MB, ~92% space saved).

- **📂 Automatic Directory Watchdog**:
  - Watches `~/Desktop` and `~/Movies` in the background with file-write debouncing.
  - As soon as macOS finishes recording, it automatically indexes the video in the background without UI freeze.

- **🎯 Drag & Drop**:
  - Drag any `.mov`, `.mp4`, `.png`, or `.jpg` directly into the window to index immediately.

---

## 🛠 Installation & Quickstart

### 1. Clone & Set Up Virtual Environment

```bash
cd "Screenrecord Manager"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Launch the Desktop GUI

```bash
python main.py
```

### 3. CLI Commands

```bash
# Index a video or an entire directory of recordings:
python main.py index ~/Desktop

# Instant full-text search from terminal:
python main.py search "TypeError"

# View indexed library statistics:
python main.py stats

# Run the background watcher daemon in terminal:
python main.py watch
```

---

## 🧪 Automated Test Suite

Run the full automated test suite (verifying SQLite FTS5, Apple Vision OCR, categorization, privacy redactor, and video keyframing):

```bash
python -m unittest tests/test_core.py
```

---

## 💼 Why This Stands Out on a Resume

| Typical Portfolio Project | Screenrecord Manager |
| :--- | :--- |
| Generic LangChain / OpenAI wrapper | Native multi-modal systems pipeline (Video + Computer Vision + Full-Text Search) |
| Uses slow external CLI binaries | Deep macOS integration via PyObjC & Apple Vision Neural Engine |
| No hardware optimization | Apple VideoToolbox hardware acceleration + non-blocking Qt multithreading |
| Unusable on real-world local files | Solves a daily MacBook pain (unsearchable desktop recordings + SSD bloat) |
