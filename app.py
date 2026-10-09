"""Punto de entrada de PlacaPro: ``python app.py``.

Arranque: log → ``QApplication`` → base SQLite (migrar + datos iniciales) → servicios →
``MainWindow`` con el último proyecto (o la demo, que se optimiza sola la primera vez).
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from database.database import Database
from database.seed import seed
from services.app_services import AppServices
from ui.main_window import MainWindow
from ui.theme import apply_theme
from ui.workers import GIL_SWITCH_INTERVAL_S
from utils.constants import APP_DATA_DIR, APP_NAME, ORGANIZATION

LOG_PATH = APP_DATA_DIR / "placapro.log"
log = logging.getLogger("placapro")


def setup_logging(path: Path = LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8")],
    )


def install_exception_hook(log_path: Path = LOG_PATH) -> None:
    """Toda excepción no capturada (también en slots de Qt) se registra y se informa con
    un diálogo, en lugar de cerrar la aplicación sin aviso."""

    def hook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Excepción no capturada\n%s", detail)
        if QApplication.instance() is not None:
            box = QMessageBox(QMessageBox.Icon.Critical, APP_NAME, "Ocurrió un error inesperado.")
            box.setInformativeText(f"{exc_type.__name__}: {exc}\n\nDetalle en {log_path}")
            box.setDetailedText(detail)
            box.exec()

    sys.excepthook = hook


def create_main_window(
    db: Database | None = None,
    settings: QSettings | None = None,
    *,
    time_budget_s: float | None = None,
    optimize_demo: bool = True,
) -> MainWindow:
    """Abre/migra la base, carga los datos iniciales y arma la ventana con la demo o el
    último proyecto abierto. En el primer arranque (base nueva) la demo se optimiza sola."""
    if db is None:
        db = Database.open_default()
    else:
        db.migrate()
    demo = seed(db)
    window = MainWindow(
        AppServices.from_db(db),
        settings if settings is not None else QSettings(ORGANIZATION, APP_NAME),
        time_budget_s=time_budget_s,
    )
    window.open_initial_project(demo.demo_project_id)
    if optimize_demo and demo.seeded and window.project.id == demo.demo_project_id:
        window.optimize()
    return window


def main() -> int:
    setup_logging()
    install_exception_hook()
    sys.setswitchinterval(GIL_SWITCH_INTERVAL_S)  # UI fluida mientras optimiza
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORGANIZATION)
    apply_theme(app)
    window = create_main_window()
    window.show()
    log.info("%s iniciado", APP_NAME)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
