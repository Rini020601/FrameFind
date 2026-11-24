"""
Main Window for Screenrecord Manager Desktop Application
Integrates the search bar, category filters, results list, video player,
inspector tabs, background indexing worker thread, and directory watcher.
"""

import os
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QSplitter,
    QProgressBar, QFileDialog, QMessageBox, QFrame,
    QButtonGroup
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from core.database import SearchDatabase
from core.indexer import IndexerPipeline
from core.watcher import CaptureWatcher
from gui.theme import DARK_THEME_QSS
from gui.results_list import ResultsListWidget
from gui.player_widget import VideoPlayerWidget, find_matching_boxes
from gui.chapters_widget import ChaptersInspectorWidget
from gui.menubar import MenuBarTray


class IndexWorker(QThread):
    progress_signal = Signal(float, str)
    finished_signal = Signal(str, int)  # file_path, record_id
    error_signal = Signal(str, str)     # file_path, error_msg

    def __init__(self, file_paths: list, db: SearchDatabase, auto_rename: bool = True):
        super().__init__()
        self.file_paths = file_paths
        self.db = db
        self.auto_rename = auto_rename

    def run(self):
        pipeline = IndexerPipeline(db=self.db, auto_rename=self.auto_rename)
        total = len(self.file_paths)
        for i, path in enumerate(self.file_paths):
            def on_progress(pct, msg):
                overall_pct = (i + pct) / total
                self.progress_signal.emit(overall_pct, f"[{i+1}/{total}] {msg}")

            try:
                rec_id = pipeline.index_file(path, progress_cb=on_progress)
                if rec_id is not None:
                    self.finished_signal.emit(path, rec_id)
            except Exception as e:
                self.error_signal.emit(path, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screenrecord Manager — Intelligent OCR & Video Indexer")
        self.resize(1280, 840)
        self.setAcceptDrops(True)

        self.db = SearchDatabase()
        self.current_filter_type = "all"
        self.current_category = "all"
        self.auto_rename_enabled = True

        self._init_ui()
        self._init_watcher()
        self._init_menubar()
        self._refresh_library()

    def _init_ui(self):
        self.setStyleSheet(DARK_THEME_QSS)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Header Bar
        header = QFrame()
        header.setObjectName("headerPanel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 10)
        header_layout.setSpacing(10)

        # Top row: Brand + Actions
        top_row = QHBoxLayout()
        logo_label = QLabel("⚡ Screenrecord Manager")
        logo_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        top_row.addWidget(logo_label)

        self.watcher_badge = QLabel("🟢 Watcher: Desktop Active")
        self.watcher_badge.setObjectName("badge")
        top_row.addWidget(self.watcher_badge)

        top_row.addStretch()

        self.auto_rename_btn = QPushButton("✨ Auto-Rename: ON")
        self.auto_rename_btn.setObjectName("filterChip")
        self.auto_rename_btn.setCheckable(True)
        self.auto_rename_btn.setChecked(True)
        self.auto_rename_btn.clicked.connect(self._toggle_auto_rename)
        top_row.addWidget(self.auto_rename_btn)

        self.daemon_btn = QPushButton("⚙️ Background Service")
        self.daemon_btn.clicked.connect(self._show_daemon_dialog)
        top_row.addWidget(self.daemon_btn)

        self.stats_btn = QPushButton("📊 Library Stats")
        self.stats_btn.clicked.connect(self._show_stats_dialog)
        top_row.addWidget(self.stats_btn)

        self.index_btn = QPushButton("+ Index Media...")
        self.index_btn.setObjectName("primaryBtn")
        self.index_btn.clicked.connect(self._on_choose_files)
        top_row.addWidget(self.index_btn)

        header_layout.addLayout(top_row)

        # Search Bar & Filter Chips Row
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchBar")
        self.search_input.setPlaceholderText("🔍 Search any text, error message, code snippet, or slide title across recordings...")
        self.search_input.setClearButtonEnabled(True)

        # Debounce timer for search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(280)
        self.search_timer.timeout.connect(self._execute_search)
        self.search_input.textChanged.connect(self.search_timer.start)

        search_row.addWidget(self.search_input, stretch=1)
        header_layout.addLayout(search_row)

        # Filter Chips Row
        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)

        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)

        filters = [
            ("All Captures", "all", "all"),
            ("🎬 Videos Only", "video", "all"),
            ("📸 Screenshots", "screenshot", "all"),
            ("💻 Code & Terminal", "all", "Code & Terminal"),
            ("📊 Slides & Presentations", "all", "Slides & Presentation"),
            ("💬 Meetings & Chat", "all", "Meeting & Chat"),
        ]

        for idx, (label, f_type, cat) in enumerate(filters):
            btn = QPushButton(label)
            btn.setObjectName("filterChip")
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, t=f_type, c=cat: self._on_filter_changed(t, c))
            self.filter_group.addButton(btn, idx)
            chips_row.addWidget(btn)

        chips_row.addStretch()
        header_layout.addLayout(chips_row)

        main_layout.addWidget(header)

        # 2. Progress Bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #3b82f6; } QProgressBar { border: none; background: #202024; }")
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        self.status_msg_label = QLabel()
        self.status_msg_label.setStyleSheet("padding: 2px 14px; color: #60a5fa; font-size: 11px; background: #202024;")
        self.status_msg_label.hide()
        main_layout.addWidget(self.status_msg_label)

        # 3. Main Splitter View (Left: Results, Right: Player + Inspector)
        splitter = QSplitter(Qt.Horizontal)

        # Left Container (Results list)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)

        self.results_list = ResultsListWidget()
        self.results_list.item_selected_signal.connect(self._on_item_selected)
        left_layout.addWidget(self.results_list)

        splitter.addWidget(left_widget)

        # Right Container (Vertical Splitter: Top Player, Bottom Tabs)
        right_splitter = QSplitter(Qt.Vertical)

        self.player_widget = VideoPlayerWidget()
        right_splitter.addWidget(self.player_widget)

        self.inspector_widget = ChaptersInspectorWidget()
        self.inspector_widget.jump_to_timestamp_signal.connect(self.player_widget.jump_to)
        self.inspector_widget.file_compressed_signal.connect(self._on_file_compressed)
        self.inspector_widget.file_renamed_signal.connect(self._on_file_renamed)
        right_splitter.addWidget(self.inspector_widget)

        # Connect player position signal to chapters highlight
        self.player_widget.position_changed_sec.connect(self.inspector_widget.update_active_timestamp)

        right_splitter.setSizes([460, 260])
        splitter.addWidget(right_splitter)

        splitter.setSizes([440, 840])
        main_layout.addWidget(splitter, stretch=1)

    def _init_watcher(self):
        """Start background directory watcher on ~/Desktop for automatic capture indexing."""
        desktop_dir = os.path.expanduser("~/Desktop")
        self.watcher = CaptureWatcher(
            watch_dirs=[desktop_dir],
            on_file_detected=self._on_watcher_file_detected
        )
        self.watcher.start()

    def _init_menubar(self):
        """Attach lightweight macOS menu bar tray icon."""
        self.menubar_tray = MenuBarTray(
            parent=self,
            db=self.db,
            on_open_search=self._focus_search,
            on_toggle_auto_rename=self._toggle_auto_rename_from_tray,
            on_cleanup_orphans=self._run_orphan_cleanup,
            get_auto_rename_state=lambda: self.auto_rename_enabled,
        )

    def _focus_search(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _toggle_auto_rename_from_tray(self):
        self.auto_rename_btn.setChecked(not self.auto_rename_enabled)
        self._toggle_auto_rename()

    def _run_orphan_cleanup(self):
        result = self.db.cleanup_orphans()
        self._refresh_library()
        QMessageBox.information(
            self,
            "Orphan Cleanup Complete",
            f"Removed {result['removed_records']} missing file record(s) and "
            f"{result['removed_thumbnails']} unreferenced thumbnail(s).",
        )

    def _on_watcher_file_detected(self, file_path: str):
        """Called by background watchdog thread when macOS writes a new recording."""
        QTimer.singleShot(0, lambda: self._start_indexing([file_path]))

    def _on_filter_changed(self, f_type: str, category: str):
        self.current_filter_type = f_type
        self.current_category = category
        self._execute_search()

    def _execute_search(self):
        query = self.search_input.text()
        results = self.db.search(
            query=query,
            file_type=self.current_filter_type,
            category=self.current_category
        )
        self.results_list.set_results(results)

    def _refresh_library(self):
        self._execute_search()
        if hasattr(self, "menubar_tray") and self.menubar_tray:
            self.menubar_tray.refresh_menu()

    def _on_item_selected(self, item_data: dict):
        rec_id = item_data.get("record_id")
        if not rec_id:
            return

        record = self.db.get_record(rec_id)
        if not record:
            return

        events = self.db.get_record_events(rec_id)
        is_video = (record.get("file_type") == "video")
        ts_sec = item_data.get("timestamp_sec", 0.0)
        matching_boxes = find_matching_boxes(
            item_data.get("bounding_boxes", []),
            self.search_input.text(),
        )

        # Load into player, seek to hit timestamp, and highlight matched OCR boxes
        self.player_widget.load_media(
            file_path=record["file_path"],
            is_video=is_video,
            jump_to_sec=ts_sec,
            highlight_boxes=matching_boxes,
        )

        # Load chapters and OCR text into inspector
        self.inspector_widget.load_record_events(record, events)

    def _on_choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Screen Recordings or Screenshots to Index",
            os.path.expanduser("~/Desktop"),
            "Media Files (*.mov *.mp4 *.png *.jpg *.jpeg)"
        )
        if files:
            self._start_indexing(files)

    def _start_indexing(self, file_paths: list):
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_msg_label.setText(f"Starting indexing of {len(file_paths)} file(s)...")
        self.status_msg_label.show()

        self.worker = IndexWorker(file_paths, self.db, auto_rename=self.auto_rename_enabled)
        self.worker.progress_signal.connect(self._on_index_progress)
        self.worker.finished_signal.connect(self._on_index_single_finished)
        self.worker.finished.connect(self._on_index_all_done)
        self.worker.start()

    def _toggle_auto_rename(self):
        self.auto_rename_enabled = self.auto_rename_btn.isChecked()
        state = "ON" if self.auto_rename_enabled else "OFF"
        self.auto_rename_btn.setText(f"✨ Auto-Rename: {state}")

    def _on_file_renamed(self, record_id: int, new_path: str, new_name: str):
        self.db.update_record_file_path(record_id, new_path, new_name)
        self._refresh_library()
        self.player_widget.load_media(
            new_path,
            is_video=new_path.lower().endswith(('.mov', '.mp4', '.m4v'))
        )

    def _on_index_progress(self, pct: float, msg: str):
        self.progress_bar.setValue(int(pct * 100))
        self.status_msg_label.setText(msg)

    def _on_index_single_finished(self, file_path: str, rec_id: int):
        self._refresh_library()

    def _on_index_all_done(self):
        self.progress_bar.hide()
        self.status_msg_label.setText("✅ Indexing complete!")
        QTimer.singleShot(2500, self.status_msg_label.hide)
        self._refresh_library()

    def _on_file_compressed(self, compressed_path: str):
        # Auto index the newly compressed video
        self._start_indexing([compressed_path])

    def _show_stats_dialog(self):
        stats = self.db.get_stats()
        hrs = round(stats.get("total_duration_sec", 0.0) / 3600.0, 2)
        gb = round(stats.get("total_size_bytes", 0) / (1024 * 1024 * 1024), 2)
        msg = (
            f"📊 <b>Library Overview</b><br><br>"
            f"• <b>Total Videos Indexed:</b> {stats.get('total_videos', 0)}<br>"
            f"• <b>Total Screenshots:</b> {stats.get('total_screenshots', 0)}<br>"
            f"• <b>Total Keyframes / Chapters:</b> {stats.get('total_indexed_events', 0)}<br>"
            f"• <b>Total Video Duration:</b> {hrs} hours<br>"
            f"• <b>Total Indexed Storage:</b> {gb} GB<br><br>"
            f"<i>Powered by Apple Silicon Vision Neural Engine & SQLite FTS5</i>"
        )
        QMessageBox.information(self, "Screenrecord Manager Stats", msg)

    def _show_daemon_dialog(self):
        from daemon import get_launch_agent_status, install_launch_agent, uninstall_launch_agent

        is_installed, is_running = get_launch_agent_status()

        status_str = "🟢 Active (Running on macOS Startup)" if is_running else ("🟡 Installed (Idle)" if is_installed else "🔴 Not Installed")

        msg = QMessageBox(self)
        msg.setWindowTitle("macOS Background Auto-Renamer Service")
        msg.setText(
            f"<b>Zero-Touch Background Auto-Renamer</b><br><br>"
            f"Status: <b>{status_str}</b><br><br>"
            f"When installed, macOS will automatically run the auto-renamer in the background on startup. "
            f"Whenever you record a video (Cmd+Shift+5) or take a screenshot, it will be automatically "
            f"analyzed with Apple Vision OCR and renamed right in Finder without needing to open this app."
        )

        install_btn = msg.addButton("🚀 Install Login Service", QMessageBox.ActionRole)
        uninstall_btn = msg.addButton("🛑 Uninstall Service", QMessageBox.ActionRole)
        close_btn = msg.addButton("Close", QMessageBox.RejectRole)

        msg.exec()

        if msg.clickedButton() == install_btn:
            install_launch_agent()
            QMessageBox.information(self, "Installed", "macOS Background Auto-Renamer installed successfully!\nCaptures in Finder will now be automatically renamed.")
        elif msg.clickedButton() == uninstall_btn:
            uninstall_launch_agent()
            QMessageBox.information(self, "Uninstalled", "Background service uninstalled.")

    # Drag and Drop handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if os.path.isfile(u.toLocalFile())]
        if files:
            self._start_indexing(files)

    def closeEvent(self, event):
        if hasattr(self, 'watcher') and self.watcher:
            self.watcher.stop()
        if hasattr(self, 'menubar_tray') and self.menubar_tray:
            self.menubar_tray.hide()
        event.accept()
