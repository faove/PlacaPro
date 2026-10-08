import logging
import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

import app
from database.database import Database
from utils.constants import APP_NAME


@pytest.mark.ui
def test_main_window_opens(qtbot, tmp_path):
    db = Database(":memory:")
    window = app.create_main_window(
        db, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    window.show()
    assert window.isVisible()
    assert window.windowTitle().endswith(f"— {APP_NAME}")
    window.close()


@pytest.mark.ui
def test_exception_hook_logs_and_shows_dialog(qtbot, tmp_path, monkeypatch, caplog):
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.informativeText()))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    app.install_exception_hook(tmp_path / "x.log")
    try:
        raise ValueError("boom")
    except ValueError:
        with caplog.at_level(logging.ERROR, logger="placapro"):
            sys.excepthook(*sys.exc_info())
    assert "boom" in caplog.text and "Traceback" in caplog.text
    assert shown and "ValueError: boom" in shown[0]


def test_setup_logging_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(logging.root, "handlers", [])
    path = tmp_path / "logs" / "placapro.log"
    app.setup_logging(path)
    logging.getLogger("placapro").info("hola")
    for handler in logging.root.handlers:
        handler.flush()
    assert "hola" in path.read_text(encoding="utf-8")
