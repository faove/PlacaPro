"""Punto de entrada de PlacaPro: ``python app.py``."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from utils.constants import APP_NAME, APP_VERSION, ORGANIZATION


def create_main_window() -> QMainWindow:
    """Ventana principal provisional (sprint 0). Se reemplaza por ui.main_window en el sprint 4."""
    window = QMainWindow()
    window.setWindowTitle(APP_NAME)
    window.resize(1280, 800)
    placeholder = QLabel(f"{APP_NAME} {APP_VERSION} — en construcción")
    placeholder.setMargin(24)
    window.setCentralWidget(placeholder)
    return window


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORGANIZATION)
    window = create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
