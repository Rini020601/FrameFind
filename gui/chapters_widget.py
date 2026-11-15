"""
Inspector & Chapters Widget for Screenrecord Manager
Provides timestamp chapter navigation, full-frame OCR text inspection,
1-click privacy redaction, and Apple VideoToolbox compression controls.
"""

import os
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QListWidget, QListWidgetItem, QTextEdit, QPushButton,
    QLabel, QMessageBox, QFileDialog, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QClipboard
from PIL import Image

from core.redactor import PrivacyRedactor
from core.compressor import VideoCompressor


class ChaptersInspectorWidget(QWidget):
    jump_to_timestamp_signal = Signal(float)
    file_compressed_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_record = None
        self.current_events = []
        self.active_event_idx = -1

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        # Tab 1: Chapters & Timestamps
        self.tab_chapters = QWidget()
        ch_layout = QVBoxLayout(self.tab_chapters)
        ch_layout.setContentsMargins(6, 6, 6, 6)

        self.chapters_list = QListWidget()
        self.chapters_list.itemClicked.connect(self._on_chapter_clicked)
        ch_layout.addWidget(self.chapters_list)
        self.tabs.addTab(self.tab_chapters, "🕒 Chapters & Events")

        # Tab 2: OCR Text Inspector
        self.tab_ocr = QWidget()
        ocr_layout = QVBoxLayout(self.tab_ocr)
        ocr_layout.setContentsMargins(6, 6, 6, 6)

        self.ocr_text_edit = QTextEdit()
        self.ocr_text_edit.setReadOnly(True)
        self.ocr_text_edit.setPlaceholderText("Extracted text for the current timestamp will appear here...")
        ocr_layout.addWidget(self.ocr_text_edit)

        ocr_btn_row = QHBoxLayout()
        self.copy_btn = QPushButton("📋 Copy Text / Code")
        self.copy_btn.clicked.connect(self._copy_ocr_text)
        ocr_btn_row.addWidget(self.copy_btn)
        ocr_btn_row.addStretch()
        ocr_layout.addLayout(ocr_btn_row)

        self.tabs.addTab(self.tab_ocr, "📝 OCR Text")

        # Tab 3: Privacy Redactor
        self.tab_redact = QWidget()
        redact_layout = QVBoxLayout(self.tab_redact)
        redact_layout.setContentsMargins(8, 8, 8, 8)
        redact_layout.setSpacing(8)

        self.redact_status_label = QLabel("Scan for sensitive API keys, emails, or tokens in this capture.")
        self.redact_status_label.setWordWrap(True)
        self.redact_status_label.setStyleSheet("color: #a1a1aa;")
        redact_layout.addWidget(self.redact_status_label)

        self.secrets_list = QListWidget()
        redact_layout.addWidget(self.secrets_list)

        redact_btn_row = QHBoxLayout()
        self.redact_frame_btn = QPushButton("🔒 1-Click Blur & Export Frame")
        self.redact_frame_btn.setObjectName("primaryBtn")
        self.redact_frame_btn.clicked.connect(self._redact_current_frame)
        redact_btn_row.addWidget(self.redact_frame_btn)
        redact_layout.addLayout(redact_btn_row)

        self.tabs.addTab(self.tab_redact, "🔒 Privacy Redactor")

        # Tab 4: Smart Compressor
        self.tab_compress = QWidget()
        comp_layout = QVBoxLayout(self.tab_compress)
        comp_layout.setContentsMargins(12, 12, 12, 12)
        comp_layout.setSpacing(10)

        self.comp_info_label = QLabel("Apple VideoToolbox Hardware Compression\nReduce bloated screen recording sizes by 80–90%.")
        self.comp_info_label.setStyleSheet("font-weight: 600; color: #f4f4f5;")
        comp_layout.addWidget(self.comp_info_label)

        self.comp_stats_label = QLabel("Select a video to see compression estimates.")
        self.comp_stats_label.setStyleSheet("color: #a1a1aa;")
        comp_layout.addWidget(self.comp_stats_label)

        self.compress_btn = QPushButton("🗜 Compress Video")
        self.compress_btn.setObjectName("successBtn")
        self.compress_btn.setFixedHeight(34)
        self.compress_btn.clicked.connect(self._run_compression)
        comp_layout.addWidget(self.compress_btn)

        comp_layout.addStretch()
        self.tabs.addTab(self.tab_compress, "🗜 Compressor")

        layout.addWidget(self.tabs)

    def load_record_events(self, record: dict, events: List[dict]):
        self.current_record = record
        self.current_events = events
        self.chapters_list.clear()
        self.secrets_list.clear()

        if not events:
            self.chapters_list.addItem("No text keyframes detected.")
            self.ocr_text_edit.setPlainText("")
            self.redact_status_label.setText("No text available for privacy scan.")
            return

        # Populate Chapters list
        for idx, ev in enumerate(events):
            sec = ev.get("timestamp_sec", 0.0)
            mins = int(sec // 60)
            secs = int(sec % 60)
            first_line = (ev.get("ocr_text") or "").strip().split("\n")[0][:45]
            if not first_line:
                first_line = "Scene Transition"

            item_text = f"⏱ {mins:02d}:{secs:02d} — {first_line}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, ev)
            self.chapters_list.addItem(item)

        # Select first event by default
        if events:
            self.update_active_timestamp(events[0].get("timestamp_sec", 0.0))

        # Check for secrets across the entire recording
        all_text = " ".join((e.get("ocr_text") or "") for e in events)
        secrets = PrivacyRedactor.detect_secrets(all_text)
        if secrets:
            self.redact_status_label.setText(f"⚠️ Found {len(secrets)} potential sensitive token(s):")
            for s in secrets:
                self.secrets_list.addItem(f"[{s['label']}] {s['value'][:8]}...{s['value'][-4:] if len(s['value']) > 12 else ''}")
        else:
            self.redact_status_label.setText("✅ No sensitive API keys or credentials detected.")

        # Update compression info
        file_size_mb = round(record.get("file_size_bytes", 0) / (1024 * 1024), 1)
        est_mb = round(file_size_mb * 0.15, 1)
        self.comp_stats_label.setText(
            f"Original Size: {file_size_mb} MB\n"
            f"Estimated Compressed Size: ~{est_mb} MB (Save ~85%)\n"
            f"Target: H.264 / Apple VideoToolbox"
        )

    def update_active_timestamp(self, current_sec: float):
        """Highlights the active chapter matching current video playback position."""
        if not self.current_events:
            return

        # Find closest event at or before current_sec
        best_idx = 0
        for i, ev in enumerate(self.current_events):
            if ev.get("timestamp_sec", 0.0) <= current_sec:
                best_idx = i
            else:
                break

        if best_idx != self.active_event_idx and best_idx < self.chapters_list.count():
            self.active_event_idx = best_idx
            self.chapters_list.setCurrentRow(best_idx)
            active_event = self.current_events[best_idx]
            self.ocr_text_edit.setPlainText(active_event.get("ocr_text", ""))

    def _on_chapter_clicked(self, item: QListWidgetItem):
        ev = item.data(Qt.UserRole)
        if ev:
            ts = ev.get("timestamp_sec", 0.0)
            self.jump_to_timestamp_signal.emit(ts)
            self.ocr_text_edit.setPlainText(ev.get("ocr_text", ""))

    def _copy_ocr_text(self):
        text = self.ocr_text_edit.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.copy_btn.setText("✅ Copied!")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.copy_btn.setText("📋 Copy Text / Code"))

    def _redact_current_frame(self):
        if not self.current_events or self.active_event_idx < 0:
            QMessageBox.information(self, "Redact", "No active frame selected.")
            return

        ev = self.current_events[self.active_event_idx]
        thumb_path = ev.get("frame_thumb_path")
        boxes = ev.get("bounding_boxes", [])

        if not thumb_path or not os.path.exists(thumb_path):
            QMessageBox.warning(self, "Redact", "No frame snapshot available for this timestamp.")
            return

        try:
            img = Image.open(thumb_path)
            redacted_img, notes = PrivacyRedactor.redact_frame(img, boxes)

            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Redacted Frame", os.path.expanduser("~/Desktop/redacted_frame.png"),
                "PNG Image (*.png)"
            )
            if save_path:
                redacted_img.save(save_path)
                msg = f"Redacted image saved to:\n{save_path}"
                if notes:
                    msg += "\n\nActions:\n" + "\n".join(notes)
                QMessageBox.information(self, "Redaction Complete", msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to redact frame: {e}")

    def _run_compression(self):
        if not self.current_record or self.current_record.get("file_type") != "video":
            QMessageBox.information(self, "Compression", "Select a video recording first.")
            return

        file_path = self.current_record["file_path"]
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Error", "Video file not found.")
            return

        self.compress_btn.setEnabled(False)
        self.compress_btn.setText("Compressing with VideoToolbox...")
        QApplication.processEvents()

        try:
            res = VideoCompressor.compress_video(file_path)
            orig_mb = round(res["orig_size_bytes"] / (1024 * 1024), 1)
            comp_mb = round(res["compressed_size_bytes"] / (1024 * 1024), 1)
            saved_mb = round(res["saved_bytes"] / (1024 * 1024), 1)

            QMessageBox.information(
                self, "Compression Success! 🚀",
                f"Video compressed in {res['elapsed_sec']}s!\n\n"
                f"Original: {orig_mb} MB\n"
                f"Compressed: {comp_mb} MB\n"
                f"Saved: {saved_mb} MB ({res['saved_percent']}%)\n\n"
                f"Saved as:\n{res['output_path']}"
            )
            self.file_compressed_signal.emit(res["output_path"])
        except Exception as e:
            QMessageBox.critical(self, "Compression Error", f"Compression failed: {e}")
        finally:
            self.compress_btn.setEnabled(True)
            self.compress_btn.setText("🗜 Compress Video")
