"""
Theme and Stylesheet for FrameFind
Modern macOS Pro Dark Theme with rounded controls, clean typography, and accent highlights.
"""

DARK_THEME_QSS = """
/* Global Window Style */
QWidget {
    background-color: #18181b;
    color: #f4f4f5;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

/* Headers and Panels */
QFrame#headerPanel {
    background-color: #202024;
    border-bottom: 1px solid #333338;
    padding: 8px 16px;
}

QFrame#sidebarPanel {
    background-color: #1e1e22;
    border-right: 1px solid #2e2e33;
}

QFrame#contentPanel {
    background-color: #18181b;
}

/* Search Bar */
QLineEdit#searchBar {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 14px;
    color: #f4f4f5;
}

QLineEdit#searchBar:focus {
    border: 1.5px solid #3b82f6;
    background-color: #2e2e33;
}

/* Buttons */
QPushButton {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    padding: 6px 14px;
    color: #e4e4e7;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #333338;
    border-color: #52525b;
}

QPushButton:pressed {
    background-color: #1e1e22;
}

QPushButton#primaryBtn {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#primaryBtn:hover {
    background-color: #1d4ed8;
}

QPushButton#successBtn {
    background-color: #059669;
    border: 1px solid #10b981;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#successBtn:hover {
    background-color: #047857;
}

/* Filter Chips (Radio / Checkable Buttons) */
QPushButton#filterChip {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    color: #a1a1aa;
}

QPushButton#filterChip:hover {
    background-color: #333338;
    color: #f4f4f5;
}

QPushButton#filterChip:checked {
    background-color: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

/* Result Item Cards / List */
QListWidget {
    background-color: #18181b;
    border: none;
    outline: none;
    padding: 6px;
}

QListWidget::item {
    background-color: #222226;
    border: 1px solid #303036;
    border-radius: 8px;
    margin-bottom: 8px;
    padding: 6px;
}

QListWidget::item:hover {
    background-color: #28282e;
    border-color: #3f3f46;
}

QListWidget::item:selected {
    background-color: #1e293b;
    border: 1.5px solid #3b82f6;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #18181b;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3f3f46;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #52525b;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Video Slider */
QSlider::groove:horizontal {
    height: 6px;
    background: #333338;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #ffffff;
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background: #60a5fa;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #2e2e33;
    background: #18181b;
    border-radius: 6px;
}

QTabBar::tab {
    background: #202024;
    color: #a1a1aa;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #18181b;
    color: #ffffff;
    border-bottom: 2px solid #3b82f6;
    font-weight: 600;
}

/* Text Edit (OCR inspector) */
QTextEdit {
    background-color: #1e1e22;
    border: 1px solid #303036;
    border-radius: 6px;
    padding: 10px;
    color: #e4e4e7;
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 12px;
}

/* Labels */
QLabel#badge {
    background-color: #312e81;
    color: #c7d2fe;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#timeBadge {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1px solid #0369a1;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}
"""
