"""
Entry point for PomodoroFocus.
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from src.core.store import Store
from src.ui.main_window import MainWindow
from src.ui.theme import APP_STYLE


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    app.setApplicationName("PomodoroFocus")

    store = Store()
    win = MainWindow(store)
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
