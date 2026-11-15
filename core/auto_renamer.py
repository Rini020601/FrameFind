"""
Background Auto-Renamer Daemon for Screenrecord Manager
Monitors macOS capture directories (Desktop, Downloads, Movies, or custom macOS screencapture location).
When a new generic recording or screenshot is saved, it automatically:
  1. Waits for macOS to finish writing the file.
  2. Samples keyframes and runs Apple Vision OCR.
  3. Synthesizes a human-readable title based on on-screen content.
  4. Automatically renames the file in Finder in-place.
  5. Sends a macOS notification banner.
  6. Updates the SQLite search index.
"""

import os
import time
import subprocess
import logging
from typing import List, Optional, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .database import SearchDatabase
from .indexer import IndexerPipeline
from .namer import SmartNamer

logger = logging.getLogger("AutoRenamer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

GENERIC_PREFIXES = (
    "Screen Recording",
    "Screen Shot",
    "ScreenShot",
    "Screenshot",
    "ScreenCapture"
)

SUPPORTED_EXTS = (".mov", ".mp4", ".m4v", ".png", ".jpg", ".jpeg")


def get_macos_screencapture_location() -> str:
    """Read the user's custom macOS screenshot save location from system defaults."""
    try:
        res = subprocess.run(
            ["defaults", "read", "com.apple.screencapture", "location"],
            capture_output=True, text=True, check=False
        )
        if res.returncode == 0 and res.stdout.strip():
            loc = os.path.expanduser(res.stdout.strip())
            if os.path.exists(loc):
                return loc
    except Exception:
        pass
    return os.path.expanduser("~/Desktop")


def send_macos_notification(title: str, message: str):
    """Display a native macOS banner notification upon successful auto-renaming."""
    # Clean quotes for AppleScript
    safe_title = title.replace('"', '\\"')
    safe_msg = message.replace('"', '\\"')
    applescript = f'display notification "{safe_msg}" with title "{safe_title}"'
    try:
        subprocess.run(["osascript", "-e", applescript], capture_output=True, check=False)
    except Exception:
        pass


class SilentCaptureHandler(FileSystemEventHandler):
    def __init__(self, pipeline: IndexerPipeline, on_renamed: Optional[Callable[[str, str], None]] = None):
        super().__init__()
        self.pipeline = pipeline
        self.on_renamed = on_renamed
        self._processing = set()

    def on_created(self, event):
        if not event.is_directory:
            self._process_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._process_file(event.src_path)

    def _process_file(self, file_path: str):
        filename = os.path.basename(file_path)

        # Ignore hidden, temporary, or already processed files
        if filename.startswith(".") or file_path in self._processing:
            return

        # Check extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTS:
            return

        # Only process generic macOS captures ("Screen Recording ...", "Screen Shot ...")
        if not any(filename.startswith(prefix) for prefix in GENERIC_PREFIXES):
            return

        self._processing.add(file_path)
        try:
            self._wait_and_rename(file_path)
        finally:
            self._processing.discard(file_path)

    def _wait_and_rename(self, file_path: str):
        logger.info(f"Detected new macOS capture: {os.path.basename(file_path)}")

        # 1. Debounce and wait for macOS to finish saving the file (file size stable)
        last_size = -1
        stable_seconds = 0
        max_wait_seconds = 45  # large screen recordings can take time to flush

        for _ in range(max_wait_seconds):
            time.sleep(1.0)
            if not os.path.exists(file_path):
                return
            try:
                curr_size = os.path.getsize(file_path)
                if curr_size > 0 and curr_size == last_size:
                    stable_seconds += 1
                    # Require 2 consecutive seconds of unchanged size to be sure write completed
                    if stable_seconds >= 2:
                        break
                else:
                    stable_seconds = 0
                last_size = curr_size
            except OSError:
                pass

        if not os.path.exists(file_path) or last_size <= 0:
            return

        old_filename = os.path.basename(file_path)
        logger.info(f"File write complete ({round(last_size / (1024*1024), 2)} MB). Analyzing content...")

        # 2. Run IndexerPipeline with auto_rename=True
        # This extracts keyframes, runs Apple Vision OCR, generates the smart name,
        # renames the file on disk in Finder, and stores the record in SQLite!
        rec_id = self.pipeline.index_file(file_path)
        if not rec_id:
            logger.warning(f"Could not index or rename: {file_path}")
            return

        # Fetch the updated record from DB to get the new filename and path
        rec = self.pipeline.db.get_record(rec_id)
        if rec and rec["file_name"] != old_filename:
            new_filename = rec["file_name"]
            new_path = rec["file_path"]
            logger.info(f"🎉 Successfully auto-renamed in Finder:\n   '{old_filename}'\n   --> '{new_filename}'")
            send_macos_notification(
                "⚡ Screenrecord Auto-Renamed",
                f"Renamed to: {new_filename}"
            )
            if self.on_renamed:
                self.on_renamed(file_path, new_path)
        else:
            logger.info(f"Retained name for: {old_filename}")


class ScreenrecordDaemon:
    def __init__(self, custom_dirs: Optional[List[str]] = None):
        self.db = SearchDatabase()
        self.pipeline = IndexerPipeline(db=self.db, auto_rename=True)

        # Build list of directories to watch
        screencapture_loc = get_macos_screencapture_location()
        default_dirs = [
            screencapture_loc,
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Movies"),
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Documents")
        ]

        # De-duplicate while preserving order and verifying existence
        seen = set()
        self.watch_dirs = []
        for d in (custom_dirs or default_dirs):
            d_norm = os.path.abspath(os.path.expanduser(d))
            if d_norm not in seen and os.path.exists(d_norm):
                seen.add(d_norm)
                self.watch_dirs.append(d_norm)

        self.observer = None
        self.is_running = False

    def start(self, blocking: bool = True):
        """Start monitoring for captures."""
        self.observer = Observer()
        handler = SilentCaptureHandler(self.pipeline)

        for d in self.watch_dirs:
            logger.info(f"👀 Watching folder for macOS captures: {d}")
            self.observer.schedule(handler, d, recursive=False)

        self.observer.start()
        self.is_running = True
        logger.info("🚀 Screenrecord Auto-Renamer background service is active!")

        if blocking:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        if self.observer and self.is_running:
            logger.info("Stopping Screenrecord Auto-Renamer service...")
            self.observer.stop()
            self.observer.join()
            self.is_running = False
