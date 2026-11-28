# ⚡ FrameFind

> **Smart Auto-Naming, Finder Spotlight Indexing, and Jump-to-Timestamp Search for macOS Screenshots & Screen Recordings — powered by Apple Vision OCR, SQLite FTS5, and PySide6.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![macOS](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon%20%2F%20Intel)-black.svg)](https://apple.com)
[![Apple Vision](https://img.shields.io/badge/OCR-Apple%20Vision%20(Neural%20Engine)-purple.svg)](https://developer.apple.com/documentation/vision)
[![PySide6](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt-green.svg)](https://www.qt.io/)
[![SQLite FTS5](https://img.shields.io/badge/Search-SQLite%20FTS5-orange.svg)](https://www.sqlite.org/fts5.html)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🌐 **Website:** [rini020601.github.io/FrameFind](https://rini020601.github.io/FrameFind/)

---

## 💡 The Problem

On macOS, recordings sit on the Desktop named `Screen Recording 2026-11-15 at 16.30.12.mov` with **zero searchability** and eat tens of gigabytes on MacBook Air SSDs.

If you recorded a 15-minute lecture or a bug reproduction, finding the exact 5 seconds where an error occurred requires manually dragging the scrub bar across the entire video.

**FrameFind** solves this:
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

- **✨ App-First & Heading-Aware Smart Auto-Renaming**:
  - Replaces generic macOS names (`Screenshot 2026-11-22 at ...png`, `Screen Recording ...mov`) with `<App> - <Heading/Title> (<Date>)`:
    - Screenshots & Recordings: detects the active application (via macOS menu bar or frontmost app `NSWorkspace`) and selects the largest clearly visible heading on screen.
    - Smart web context: names browser home screens after the site (e.g. `Brave Browser - YouTube (2026-11-22).png`) and ignores recommended sidebar thumbnails on YouTube watch pages.
    - Code & Apps: `VS Code - daemon.py`, `Apple Maps - McDonald's`, `Calendar - November 2026`, `Spotify - Your Library`.
  - Renames the physical file on disk and syncs the SQLite search index atomically.
  - Can be toggled on/off in the header bar or executed via 1-click `🏷️ Smart Rename` in the Inspector.

- **🔎 Search Inside Videos Directly from macOS Finder**:
  - Automatically writes deduplicated OCR words from every sampled frame into macOS Finder/Spotlight comments (`kMDItemFinderComment` + `mdimport`), so typing any word from inside a video in Finder finds that file.

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
git clone https://github.com/Rini020601/FrameFind.git
cd FrameFind
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Optional: Hardware Video Compression & Local Audio Transcription

```bash
# Required for Apple VideoToolbox hardware compression & audio extraction
brew install ffmpeg

# Optional: searchable spoken audio transcripts (Apple Silicon recommended)
pip install mlx-whisper
```

### 2. Launch the Desktop GUI

```bash
python main.py
```

### 3. Zero-Touch Background Auto-Renamer (No App Opening Required)

If you don't want to open any app and just want macOS screen recordings to **automatically rename themselves in Finder / Recents** as soon as you record:

```bash
# Option A: Install as a silent macOS startup service (starts automatically on login):
python daemon.py install

# Check service status:
python daemon.py status

# Option B: Run directly in terminal:
python daemon.py start

# To uninstall the background service:
python daemon.py uninstall
```

### 4. CLI Commands

```bash
# Index a video or an entire directory of recordings:
python main.py index ~/Desktop

# Instant full-text search from terminal:
python main.py search "TypeError"

# View indexed library statistics:
python main.py stats

# Smart-rename an existing capture:
python main.py rename "path/to/Screen Recording.mov"
```

---

## 🧪 Automated Test Suite

Run the full automated test suite (verifying SQLite FTS5, Apple Vision OCR, categorization, privacy redactor, and video keyframing):

```bash
python -m unittest tests/test_core.py
```

---

## 💼 Why This Stands Out on a Resume

| Typical Portfolio Project | FrameFind |
| :--- | :--- |
| Generic LangChain / OpenAI wrapper | Native multi-modal systems pipeline (Video + Computer Vision + Full-Text Search) |
| Uses slow external CLI binaries | Deep macOS integration via PyObjC & Apple Vision Neural Engine |
| No hardware optimization | Apple VideoToolbox hardware acceleration + non-blocking Qt multithreading |
| Unusable on real-world local files | Solves a daily MacBook pain (unsearchable desktop recordings + SSD bloat) |
