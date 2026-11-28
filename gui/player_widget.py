"""
Interactive Video & Image Player Widget for FrameFind
Supports hardware video playback, timeline scrubbing, speed control, and instant jump-to-timestamp.
"""

import os
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QComboBox, QStackedWidget, QScrollArea
)
from PySide6.QtCore import Qt, QUrl, Signal, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget


def find_matching_boxes(
    bounding_boxes: List[Dict[str, Any]],
    query: str,
) -> List[List[float]]:
    """Return normalized [x, y, w, h] boxes whose OCR text matches any query token."""
    tokens = [w.strip().lower() for w in (query or "").split() if len(w.strip()) >= 2]
    if not tokens or not bounding_boxes:
        return []

    matches: List[List[float]] = []
    for item in bounding_boxes:
        text = (item.get("text") or "").lower()
        box = item.get("box")
        if not text or not box or len(box) != 4:
            continue
        if any(tok in text for tok in tokens):
            matches.append(box)
    return matches


class _HighlightOverlay(QWidget):
    """Transparent overlay widget that draws yellow highlight boxes over matched OCR regions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._boxes: List[List[float]] = []

    def set_boxes(self, boxes: List[List[float]]):
        self._boxes = boxes or []
        self.update()

    def paintEvent(self, event):
        if not self._boxes:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fill = QColor(250, 204, 21, 80)
        pen = QPen(QColor(250, 204, 21, 235), 2)
        painter.setBrush(fill)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        for nx, ny, nw, nh in self._boxes:
            rect = QRect(int(nx * w), int(ny * h), max(4, int(nw * w)), max(4, int(nh * h)))
            painter.drawRoundedRect(rect, 3, 3)
        painter.end()


class VideoPlayerWidget(QWidget):
    position_changed_sec = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file_path = None
        self.is_video = False
        self.duration_ms = 0

        self._init_ui()
        self._init_player()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(6)

        # 1. Stacked Display (Index 0: Video, Index 1: Static Screenshot, Index 2: Empty placeholder)
        self.stack = QStackedWidget()

        # Video View + transparent highlight overlay
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #09090b; border-radius: 8px;")
        self.video_overlay = _HighlightOverlay(self.video_widget)
        self.stack.addWidget(self.video_widget)

        # Image View (for screenshots)
        self.image_scroll = QScrollArea()
        self.image_scroll.setAlignment(Qt.AlignCenter)
        self.image_scroll.setStyleSheet("background-color: #09090b; border: none; border-radius: 8px;")
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_scroll.setWidget(self.image_label)
        self.image_scroll.setWidgetResizable(True)
        self.stack.addWidget(self.image_scroll)

        # Placeholder View
        self.placeholder = QLabel("Select a recording or screenshot to preview")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("color: #71717a; font-size: 15px; background-color: #111113; border-radius: 8px;")
        self.stack.addWidget(self.placeholder)

        self.stack.setCurrentIndex(2)
        self.main_layout.addWidget(self.stack, stretch=1)

        # 2. Control Bar (visible for video)
        self.controls_widget = QWidget()
        ctrl_layout = QVBoxLayout(self.controls_widget)
        ctrl_layout.setContentsMargins(8, 4, 8, 8)
        ctrl_layout.setSpacing(4)

        # Scrubber Row
        scrub_layout = QHBoxLayout()
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #a1a1aa; font-size: 11px; min-width: 80px;")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(self._on_slider_moved)

        scrub_layout.addWidget(self.time_label)
        scrub_layout.addWidget(self.slider)
        ctrl_layout.addLayout(scrub_layout)

        # Buttons Row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setFixedWidth(80)
        self.play_btn.clicked.connect(self.toggle_play)
        btn_layout.addWidget(self.play_btn)

        self.back_btn = QPushButton("⏪ -5s")
        self.back_btn.setFixedWidth(60)
        self.back_btn.clicked.connect(lambda: self.seek_relative(-5))
        btn_layout.addWidget(self.back_btn)

        self.fwd_btn = QPushButton("⏩ +5s")
        self.fwd_btn.setFixedWidth(60)
        self.fwd_btn.clicked.connect(lambda: self.seek_relative(5))
        btn_layout.addWidget(self.fwd_btn)

        btn_layout.addStretch()

        # Playback speed dropdown
        speed_label = QLabel("Speed:")
        speed_label.setStyleSheet("color: #a1a1aa;")
        btn_layout.addWidget(speed_label)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["1.0x", "1.25x", "1.5x", "2.0x"])
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        btn_layout.addWidget(self.speed_combo)

        ctrl_layout.addLayout(btn_layout)
        self.main_layout.addWidget(self.controls_widget)
        self.controls_widget.hide()

    def _init_player(self):
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)

    def load_media(
        self,
        file_path: str,
        is_video: bool = True,
        jump_to_sec: float = 0.0,
        highlight_boxes: Optional[List[List[float]]] = None,
    ):
        self.current_file_path = file_path
        self.is_video = is_video
        boxes = highlight_boxes or []

        if not os.path.exists(file_path):
            self.stack.setCurrentIndex(2)
            self.placeholder.setText(f"File not found:\n{file_path}")
            self.controls_widget.hide()
            return

        if is_video:
            self.stack.setCurrentIndex(0)
            self.controls_widget.show()
            self.video_overlay.setGeometry(self.video_widget.rect())
            self.video_overlay.set_boxes(boxes)
            self.video_overlay.raise_()
            self.media_player.setSource(QUrl.fromLocalFile(file_path))
            if jump_to_sec > 0:
                self.jump_to(jump_to_sec)
            self.media_player.play()
            self.play_btn.setText("⏸ Pause")
        else:
            self.media_player.stop()
            self.video_overlay.set_boxes([])
            self.controls_widget.hide()
            self.stack.setCurrentIndex(1)
            pix = QPixmap(file_path)
            scaled = pix.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if boxes and not scaled.isNull():
                painter = QPainter(scaled)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setBrush(QColor(250, 204, 21, 90))
                painter.setPen(QPen(QColor(250, 204, 21, 240), 2))
                sw, sh = scaled.width(), scaled.height()
                for nx, ny, nw, nh in boxes:
                    rect = QRect(int(nx * sw), int(ny * sh), max(4, int(nw * sw)), max(4, int(nh * sh)))
                    painter.drawRoundedRect(rect, 3, 3)
                painter.end()
            self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "video_overlay") and hasattr(self, "video_widget"):
            self.video_overlay.setGeometry(self.video_widget.rect())

    def jump_to(self, sec: float):
        """Seek video to exact second."""
        if self.is_video:
            ms = int(sec * 1000)
            self.media_player.setPosition(ms)

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
            self.play_btn.setText("▶ Play")
        else:
            self.media_player.play()
            self.play_btn.setText("⏸ Pause")

    def seek_relative(self, delta_sec: float):
        new_pos = max(0, self.media_player.position() + int(delta_sec * 1000))
        self.media_player.setPosition(new_pos)

    def _on_speed_changed(self, text: str):
        speed_map = {"1.0x": 1.0, "1.25x": 1.25, "1.5x": 1.5, "2.0x": 2.0}
        self.media_player.setPlaybackRate(speed_map.get(text, 1.0))

    def _on_slider_moved(self, value: int):
        if self.duration_ms > 0:
            target_ms = int((value / 1000.0) * self.duration_ms)
            self.media_player.setPosition(target_ms)

    def _on_duration_changed(self, duration_ms: int):
        self.duration_ms = duration_ms
        self._update_time_label(self.media_player.position())

    def _on_position_changed(self, position_ms: int):
        if self.duration_ms > 0:
            pct = int((position_ms / float(self.duration_ms)) * 1000)
            self.slider.blockSignals(True)
            self.slider.setValue(pct)
            self.slider.blockSignals(False)

        self._update_time_label(position_ms)
        self.position_changed_sec.emit(position_ms / 1000.0)

    def _update_time_label(self, current_ms: int):
        cur_sec = current_ms // 1000
        dur_sec = self.duration_ms // 1000
        cur_m, cur_s = divmod(cur_sec, 60)
        dur_m, dur_s = divmod(dur_sec, 60)
        self.time_label.setText(f"{cur_m:02d}:{cur_s:02d} / {dur_m:02d}:{dur_s:02d}")
