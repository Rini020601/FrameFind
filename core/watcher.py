"""
Filesystem Watcher Daemon for Screenrecord Manager
Monitors ~/Desktop and ~/Movies for newly created macOS screen recordings and screenshots.
Debounces file writes until macOS finishes saving the file.
"""

import os
import time
import threading
import logging
from typing import Callable, List, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".mov", ".mp4", ".m4v", ".png", ".jpg", ".jpeg"}


class ScreenrecordFileHandler(FileSystemEventHandler):
    def __init__(self, on_file_ready: Callable[[str], None], debounce_sec: float = 3.0):
        super().__init__()
        self.on_file_ready = on_file_ready
        self.debounce_sec = debounce_sec
        self._processing = set()
        self._processed_signatures = {}
        self._lock = threading.Lock()

    def on_created(self, event):
        if not event.is_directory:
            self._handle_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle_file(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_file(event.dest_path)

    @staticmethod
    def _file_signature(path: str):
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns

    def _handle_file(self, path: str):
        filename = os.path.basename(path)
        # Skip temporary, hidden, or partial files
        if filename.startswith(".") or filename.endswith(".download") or filename.endswith(".crdownload"):
            return

        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTS:
            return

        with self._lock:
            if path in self._processing:
                return
            try:
                sig = self._file_signature(path)
            except OSError:
                return
            if self._processed_signatures.get(path) == sig:
                return
            self._processing.add(path)

        try:
            self._wait_until_stable_and_process(path)
        finally:
            with self._lock:
                self._processing.discard(path)
                if os.path.exists(path):
                    try:
                        if len(self._processed_signatures) >= 500:
                            self._processed_signatures.clear()
                        self._processed_signatures[path] = self._file_signature(path)
                    except OSError:
                        pass

    def _wait_until_stable_and_process(self, path: str):
        """Poll until file size stops changing (macOS finished recording/exporting)."""
        last_size = -1
        stable_count = 0

        # Max wait 30 seconds for huge recordings
        for _ in range(15):
            time.sleep(1.0)
            if not os.path.exists(path):
                return
            try:
                curr_size = os.path.getsize(path)
                if curr_size > 0 and curr_size == last_size:
                    stable_count += 1
                    if stable_count >= 2:
                        # File is fully written
                        self.on_file_ready(path)
                        return
                else:
                    stable_count = 0
                last_size = curr_size
            except OSError:
                pass


class CaptureWatcher:
    def __init__(self, watch_dirs: Optional[List[str]] = None, on_file_detected: Optional[Callable[[str], None]] = None):
        if watch_dirs is None:
            desktop = os.path.expanduser("~/Desktop")
            movies = os.path.expanduser("~/Movies")
            self.watch_dirs = [d for d in [desktop, movies] if os.path.exists(d)]
        else:
            self.watch_dirs = watch_dirs

        self.on_file_detected = on_file_detected or (lambda path: None)
        self.observer = None
        self._is_running = False

    def start(self):
        if self._is_running:
            return

        self.observer = Observer()
        handler = ScreenrecordFileHandler(self.on_file_detected)

        for d in self.watch_dirs:
            logger.info(f"Watching directory for screen captures: {d}")
            self.observer.schedule(handler, d, recursive=False)

        self.observer.start()
        self._is_running = True

    def stop(self):
        if self.observer and self._is_running:
            self.observer.stop()
            self.observer.join()
            self._is_running = False
