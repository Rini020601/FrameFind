"""
Results List Widget for FrameFind
Renders rich search results and library items with thumbnails, badges, and snippets.
"""

import os
from PySide6.QtWidgets import (
    QWidget, QListWidget, QListWidgetItem, QVBoxLayout,
    QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QIcon


class ResultCardWidget(QFrame):
    def __init__(self, item_data: dict, parent=None):
        super().__init__(parent)
        self.item_data = item_data
        self.setObjectName("resultCard")
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # 1. Thumbnail
        thumb_label = QLabel()
        thumb_label.setFixedSize(96, 54)
        thumb_label.setStyleSheet("background-color: #111113; border-radius: 4px; border: 1px solid #333338;")
        thumb_label.setAlignment(Qt.AlignCenter)

        thumb_path = self.item_data.get("thumbnail_path") or self.item_data.get("frame_thumb_path")
        if thumb_path and os.path.exists(thumb_path):
            pix = QPixmap(thumb_path).scaled(
                96, 54, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            # Crop to exact 96x54
            rect_pix = pix.copy(0, 0, min(96, pix.width()), min(54, pix.height()))
            thumb_label.setPixmap(rect_pix)
        else:
            icon_char = "🎬" if self.item_data.get("file_type") == "video" else "📸"
            thumb_label.setText(icon_char)
            thumb_label.setStyleSheet("font-size: 24px; background-color: #111113; border-radius: 4px;")

        layout.addWidget(thumb_label)

        # 2. Details Column
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(4)

        # Top row: Title + badges
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        title = QLabel(self.item_data.get("file_name", "Untitled"))
        title.setStyleSheet("font-weight: 600; font-size: 13px; color: #f4f4f5;")
        top_row.addWidget(title)
        top_row.addStretch()

        # Timestamp badge (if video & has timestamp)
        file_type = self.item_data.get("file_type", "video")
        ts_sec = self.item_data.get("timestamp_sec")
        if file_type == "video" and ts_sec is not None:
            mins = int(ts_sec // 60)
            secs = int(ts_sec % 60)
            ts_badge = QLabel(f"⏱ Jump {mins:02d}:{secs:02d}")
            ts_badge.setObjectName("timeBadge")
            top_row.addWidget(ts_badge)
        elif file_type == "screenshot":
            shot_badge = QLabel("📸 Screenshot")
            shot_badge.setObjectName("badge")
            top_row.addWidget(shot_badge)

        # Category badge
        cat = self.item_data.get("category", "General")
        cat_badge = QLabel(cat)
        cat_badge.setObjectName("badge")
        top_row.addWidget(cat_badge)

        details_layout.addLayout(top_row)

        # Snippet Row (Search match or summary)
        ocr_snippet = self.item_data.get("ocr_snippet") or ""
        if ocr_snippet:
            snippet_text = ocr_snippet.replace("<mark>", "<span style='color: #60a5fa; font-weight: bold;'>").replace("</mark>", "</span>")
            snippet_label = QLabel(f"OCR Match: {snippet_text}")
            snippet_label.setTextFormat(Qt.RichText)
            snippet_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")
            snippet_label.setWordWrap(True)
            details_layout.addWidget(snippet_label)
        else:
            # Show duration / file size if no search snippet
            dur = self.item_data.get("duration_sec", 0.0)
            size_mb = round(self.item_data.get("file_size_bytes", 0) / (1024 * 1024), 1)
            app = self.item_data.get("app_name", "macOS")
            mins = int(dur // 60)
            secs = int(dur % 60)
            dur_str = f"{mins:02d}:{secs:02d}" if file_type == "video" else "1 frame"
            sub_label = QLabel(f"App: {app} • Duration: {dur_str} • Size: {size_mb} MB")
            sub_label.setStyleSheet("color: #71717a; font-size: 11px;")
            details_layout.addWidget(sub_label)

        layout.addLayout(details_layout)


class ResultsListWidget(QListWidget):
    item_selected_signal = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.itemClicked.connect(self._on_item_clicked)

    def set_results(self, items: list):
        self.clear()
        if not items:
            placeholder = QListWidgetItem("No recordings or search matches found.")
            placeholder.setFlags(Qt.NoItemFlags)
            self.addItem(placeholder)
            return

        for data in items:
            item = QListWidgetItem()
            card = ResultCardWidget(data)
            item.setSizeHint(card.sizeHint())
            item.setData(Qt.UserRole, data)
            self.addItem(item)
            self.setItemWidget(item, card)

    def _on_item_clicked(self, list_item: QListWidgetItem):
        data = list_item.data(Qt.UserRole)
        if data:
            self.item_selected_signal.emit(data)
