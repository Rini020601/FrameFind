"""
GUI Application Launcher for Screenrecord Manager
"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from .main_window import MainWindow


def run_gui():
    # High DPI scaling attributes for Apple Retina displays
    app = QApplication(sys.argv)
    app.setApplicationName("Screenrecord Manager")
    app.setOrganizationName("ScreenrecordManager")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
