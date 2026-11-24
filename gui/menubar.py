"""
macOS Menu Bar / System Tray Integration for FrameFind (Screenrecord Manager)
Provides a lightweight menu bar icon using PySide6 QSystemTrayIcon with:
  - Quick Search (raises window & focuses search bar)
  - Pause / Resume Auto-Rename
  - Last 5 Captures (click to reveal in Finder)
  - One-click Orphan Cleanup
"""

import os
import sys
import subprocess
from typing import Callable, Optional
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt


def _build_tray_icon() -> QIcon:
    """Create a crisp 32x32 menu bar icon programmatically."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#3b82f6"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(3, 3, 26, 26, 6, 6)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("SF Pro Display", 16, QFont.Bold))
    painter.drawText(pix.rect(), Qt.AlignCenter, "F")
    painter.end()
    return QIcon(pix)


def reveal_in_finder(file_path: str):
    """Reveal a capture file in macOS Finder (or open its folder on other OS)."""
    if not file_path or not os.path.exists(file_path):
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", file_path], check=False)
        else:
            subprocess.run(["open", os.path.dirname(file_path)], check=False)
    except Exception:
        pass


class MenuBarTray:
    def __init__(
        self,
        parent,
        db,
        on_open_search: Callable[[], None],
        on_toggle_auto_rename: Callable[[], None],
        on_cleanup_orphans: Callable[[], None],
        get_auto_rename_state: Callable[[], bool],
    ):
        self.parent = parent
        self.db = db
        self.on_open_search = on_open_search
        self.on_toggle_auto_rename = on_toggle_auto_rename
        self.on_cleanup_orphans = on_cleanup_orphans
        self.get_auto_rename_state = get_auto_rename_state

        self.tray: Optional[QSystemTrayIcon] = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(_build_tray_icon(), parent)
        self.tray.setToolTip("FrameFind — Smart Screen Capture Search")
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.refresh_menu()
        self.tray.show()

    def refresh_menu(self):
        if self.tray is None:
            return

        self.menu.clear()

        status_action = self.menu.addAction("⚡ FrameFind — Active")
        status_action.setEnabled(False)
        self.menu.addSeparator()

        search_action = self.menu.addAction("🔍 Quick Search...")
        search_action.triggered.connect(self.on_open_search)

        auto_on = self.get_auto_rename_state()
        toggle_label = "⏸ Pause Auto-Rename" if auto_on else "▶ Resume Auto-Rename"
        toggle_action = self.menu.addAction(toggle_label)
        toggle_action.triggered.connect(self._handle_toggle)

        self.menu.addSeparator()
        recent_menu = self.menu.addMenu("🕒 Recent Captures")
        recents = self.db.get_recent_records(limit=5)
        if recents:
            for rec in recents:
                name = rec.get("file_name", "Untitled")
                path = rec.get("file_path", "")
                act = recent_menu.addAction(name[:50])
                act.triggered.connect(lambda checked=False, p=path: reveal_in_finder(p))
        else:
            empty_act = recent_menu.addAction("(No captures yet)")
            empty_act.setEnabled(False)

        cleanup_action = self.menu.addAction("🧹 Clean Up Orphans")
        cleanup_action.triggered.connect(self.on_cleanup_orphans)

        self.menu.addSeparator()
        quit_action = self.menu.addAction("Quit FrameFind")
        quit_action.triggered.connect(QApplication.instance().quit)

    def _handle_toggle(self):
        self.on_toggle_auto_rename()
        self.refresh_menu()

    def hide(self):
        if self.tray is not None:
            self.tray.hide()
