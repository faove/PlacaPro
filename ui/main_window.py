"""Ventana principal: tres paneles, menús de archivo/ver y ejecución de la optimización.

La ventana es dueña del ``Project`` en edición; los widgets lo modifican en el sitio y
avisan con señales. Ver docs/05-interfaz-de-usuario.md.
"""

from __future__ import annotations

import logging
from html import escape

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from models.parametros import CuttingParameters
from models.placa import PlateFormat
from models.proyecto import Project
from models.resultado import OptimizationResult
from models.validation import IssueCode, ValidationFailed, ValidationIssue
from services.app_services import AppServices
from services.optimization_service import OptimizationOutcome, PreparedOptimization
from ui.cut_list_widget import CutListWidget
from ui.cutting_diagram_widget import CuttingDiagramWidget
from ui.open_project_dialog import OpenProjectDialog
from ui.parameters_widget import ParametersWidget
from ui.pieces_widget import PiecesWidget
from ui.plate_widget import PlateWidget
from ui.project_widget import ProjectWidget
from ui.result_widget import ResultWidget
from ui.units_display import UnitsDisplay
from ui.validation_panel import ValidationPanel
from ui.workers import OptimizationWorker
from utils.constants import APP_NAME
from utils.units import Unit

log = logging.getLogger(__name__)

PAGE_PROJECT, PAGE_PLATE, PAGE_PIECES, PAGE_PARAMETERS = range(4)
VALIDATION_DELAY_MS = 250

# Claves de QSettings
KEY_GEOMETRY = "window/geometry"
KEY_STATE = "window/state"
KEY_SPLITTER = "window/splitter"
KEY_CENTER_SPLITTER = "window/center_splitter"
KEY_UNIT = "view/unit"
KEY_LAST_PROJECT = "project/last_id"


def _scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    return area


class MainWindow(QMainWindow):
    """Emite ``optimization_finished(OptimizationOutcome)`` al terminar una optimización."""

    optimization_finished = Signal(object)

    def __init__(
        self,
        services: AppServices,
        settings: QSettings,
        *,
        time_budget_s: float | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.settings = settings
        self.time_budget_s = time_budget_s
        self.project: Project = services.projects.new_project()
        self.plate: PlateFormat | None = None
        self.dirty = False
        self._worker: OptimizationWorker | None = None
        self._prepared: PreparedOptimization | None = None
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(1)

        unit_symbol = str(settings.value(KEY_UNIT, Unit.MM.symbol))
        unit = next((u for u in Unit if u.symbol == unit_symbol), Unit.MM)
        self.units = UnitsDisplay(unit, self)

        self._validation_timer = QTimer(self)
        self._validation_timer.setSingleShot(True)
        self._validation_timer.setInterval(VALIDATION_DELAY_MS)
        self._validation_timer.timeout.connect(self.run_validation)

        self._build_widgets()
        self._build_menus()
        self._connect_signals()
        self._restore_settings()
        self.load_project(self.project)

    # ------------------------------------------------------------------ construcción
    def _build_widgets(self) -> None:
        s = self.services
        self.project_widget = ProjectWidget(self.units)
        self.plate_widget = PlateWidget(s.plates, s.inventory, self.units)
        self.pieces_widget = PiecesWidget(self.units)
        self.parameters_widget = ParametersWidget(self.units)

        self.toolbox = QToolBox()
        self.toolbox.addItem(_scrollable(self.project_widget), "PROYECTO")
        self.toolbox.addItem(_scrollable(self.plate_widget), "PLACA")
        self.toolbox.addItem(self.pieces_widget, "PIEZAS")
        self.toolbox.addItem(_scrollable(self.parameters_widget), "PARÁMETROS")
        self.toolbox.setCurrentIndex(PAGE_PIECES)

        self.optimize_button = QPushButton("OPTIMIZAR CORTES")
        self.optimize_button.setObjectName("optimizeButton")
        self.optimize_button.setShortcut(QKeySequence("F5"))
        self.optimize_button.setToolTip("Calcular la distribución de cortes (F5)")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.cancel_button = QPushButton("Cancelar")
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.cancel_button)
        self.progress_bar.hide()
        self.cancel_button.hide()

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.toolbox, 1)
        left_layout.addWidget(self.optimize_button)
        left_layout.addLayout(progress_row)

        self.diagram_widget = CuttingDiagramWidget(self.units)
        # Pestañas inferiores: Lista de cortes, Secuencia y Mensajes de validación.
        self.cut_list_widget = CutListWidget(self.units)
        self.bottom_tabs: QTabWidget = self.cut_list_widget
        self.validation_panel = ValidationPanel()
        self.messages_tab = self.bottom_tabs.addTab(self.validation_panel, "Mensajes")
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.center_splitter.addWidget(self.diagram_widget)
        self.center_splitter.addWidget(self.bottom_tabs)
        self.center_splitter.setStretchFactor(0, 3)
        self.center_splitter.setStretchFactor(1, 1)
        self.center_splitter.setSizes([520, 220])

        self.result_widget = ResultWidget(self.units)
        self.result: OptimizationResult | None = None

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.center_splitter)
        self.splitter.addWidget(self.result_widget)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([480, 640, 340])
        self.setCentralWidget(self.splitter)

        self.status_project = QLabel()
        self.status_plate = QLabel()
        self.status_message = QLabel()
        bar = self.statusBar()
        bar.addWidget(self.status_project)
        bar.addWidget(self.status_plate)
        bar.addWidget(self.status_message, 1)
        self.resize(1440, 860)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Archivo")
        self.action_new = self._action(file_menu, "&Nuevo", self.new_project, QKeySequence.New)
        self.action_open = self._action(
            file_menu, "&Abrir…", self.open_project_dialog, QKeySequence.Open
        )
        file_menu.addSeparator()
        self.action_save = self._action(file_menu, "&Guardar", self.save, QKeySequence.Save)
        self.action_save_as = self._action(
            file_menu, "Guardar &como…", self.save_as, QKeySequence.SaveAs
        )
        self.action_duplicate = self._action(file_menu, "&Duplicar", self.duplicate_project)
        self.action_delete = self._action(file_menu, "&Eliminar…", self.delete_project)
        file_menu.addSeparator()
        self._action(file_menu, "&Salir", self.close, QKeySequence.Quit)

        view_menu = self.menuBar().addMenu("&Ver")
        units_menu = view_menu.addMenu("&Unidades")
        self.unit_actions: dict[Unit, QAction] = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        for unit in Unit:
            action = QAction(unit.symbol, self, checkable=True)
            action.setChecked(unit is self.units.unit)
            action.triggered.connect(lambda _checked, u=unit: self.set_unit(u))
            group.addAction(action)
            units_menu.addAction(action)
            self.unit_actions[unit] = action

    def _action(self, menu, text, slot, shortcut=None) -> QAction:  # type: ignore[no-untyped-def]
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: slot())
        menu.addAction(action)
        return action

    def _connect_signals(self) -> None:
        self.project_widget.changed.connect(self.mark_dirty)
        self.project_widget.furniture_changed.connect(self.pieces_widget.refresh_furniture)
        self.project_widget.furniture_selected.connect(self.pieces_widget.select_furniture)
        self.pieces_widget.furniture_combo.currentIndexChanged.connect(
            self.project_widget.select_furniture
        )
        self.pieces_widget.changed.connect(self.mark_dirty)
        self.plate_widget.plate_selected.connect(self._on_plate_selected)
        self.plate_widget.plates_changed.connect(self._refresh_context)
        self.parameters_widget.changed.connect(self._on_params_changed)
        self.validation_panel.issue_activated.connect(self.focus_issue)
        self.diagram_widget.piece_selected.connect(self.cut_list_widget.select_piece)
        self.diagram_widget.cut_selected.connect(self.cut_list_widget.select_cut)
        self.cut_list_widget.piece_selected.connect(self.diagram_widget.select_piece)
        self.cut_list_widget.cut_selected.connect(self.diagram_widget.select_cut)
        self.result_widget.sheet_activated.connect(self.diagram_widget.show_sheet)
        self.optimize_button.clicked.connect(self.optimize)
        self.cancel_button.clicked.connect(self.cancel_optimization)

    # ------------------------------------------------------------------ settings
    def _restore_settings(self) -> None:
        geometry = self.settings.value(KEY_GEOMETRY)
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value(KEY_STATE)
        if state is not None:
            self.restoreState(state)
        splitter = self.settings.value(KEY_SPLITTER)
        if splitter is not None:
            self.splitter.restoreState(splitter)
        center = self.settings.value(KEY_CENTER_SPLITTER)
        if center is not None:
            self.center_splitter.restoreState(center)

    def save_settings(self) -> None:
        self.settings.setValue(KEY_GEOMETRY, self.saveGeometry())
        self.settings.setValue(KEY_STATE, self.saveState())
        self.settings.setValue(KEY_SPLITTER, self.splitter.saveState())
        self.settings.setValue(KEY_CENTER_SPLITTER, self.center_splitter.saveState())
        self.settings.setValue(KEY_UNIT, self.units.symbol)
        if self.project.id is not None:
            self.settings.setValue(KEY_LAST_PROJECT, self.project.id)
        self.settings.sync()

    def open_initial_project(self, demo_project_id: int | None = None) -> None:
        """Último proyecto abierto; si no existe, la demo; si no, el más reciente o uno nuevo."""
        candidates: list[int] = []
        last = self.settings.value(KEY_LAST_PROJECT)
        if last not in (None, ""):
            candidates.append(int(last))
        if demo_project_id is not None:
            candidates.append(demo_project_id)
        candidates += [p.id for p in self.services.projects.list_projects()]
        for project_id in candidates:
            if self.services.projects.projects.exists(project_id):
                self.open_project(project_id, ask_save=False)
                return
        self.load_project(self._fresh_project())

    # ------------------------------------------------------------------ proyecto
    def _fresh_project(self) -> Project:
        plate_id = self.project.plate_format_id
        if plate_id is None:
            formats = self.services.plates.list_formats()
            plate_id = formats[0].id if formats else None
        return self.services.projects.new_project(
            plate_format_id=plate_id, params=self.project.params
        )

    def load_project(self, project: Project, result: OptimizationResult | None = None) -> None:
        self.project = project
        self.project_widget.set_project(project)
        self.pieces_widget.set_project(project)
        self.plate_widget.set_selected_plate(project.plate_format_id)
        self.parameters_widget.set_params(project.params)
        self._refresh_context()
        self.show_result(result)
        self.status_message.setText("")
        self.set_dirty(False)
        self.run_validation()

    def open_project(self, project_id: int, *, ask_save: bool = True) -> bool:
        if ask_save and not self.maybe_save():
            return False
        project = self.services.projects.open(project_id)
        self.load_project(project, self.services.optimization.latest_result(project_id))
        self.settings.setValue(KEY_LAST_PROJECT, project_id)
        return True

    def new_project(self) -> bool:
        if not self.maybe_save():
            return False
        self.load_project(self._fresh_project())
        return True

    def open_project_dialog(self) -> bool:
        if not self.maybe_save():
            return False
        dialog = OpenProjectDialog(self.services.projects.list_projects(), self)
        if dialog.exec() != OpenProjectDialog.DialogCode.Accepted:
            return False
        project_id = dialog.selected_project_id()
        return project_id is not None and self.open_project(project_id, ask_save=False)

    def save(self) -> bool:
        try:
            self.services.projects.save(self.project)
        except ValidationFailed as exc:
            QMessageBox.warning(self, "No se pudo guardar", str(exc))
            return False
        self.project_widget.set_project(self.project)  # nombre normalizado
        self.settings.setValue(KEY_LAST_PROJECT, self.project.id)
        self.set_dirty(False)
        self.status_message.setText(f"Proyecto «{self.project.name}» guardado")
        return True

    def save_as(self, name: str | None = None) -> bool:
        if name is None:
            name, ok = QInputDialog.getText(
                self, "Guardar como", "Nombre del nuevo proyecto:", text=self.project.name
            )
            if not ok:
                return False
        try:
            copy = self.services.projects.save_as(self.project, name)
        except ValidationFailed as exc:
            QMessageBox.warning(self, "No se pudo guardar", str(exc))
            return False
        self.load_project(copy)
        self.settings.setValue(KEY_LAST_PROJECT, copy.id)
        self.status_message.setText(f"Guardado como «{copy.name}»")
        return True

    def duplicate_project(self) -> bool:
        """Duplica el proyecto guardado y abre la copia (pide guardar los cambios antes)."""
        if self.project.id is None:
            return self.save_as(f"{self.project.name} (copia)")
        if not self.maybe_save():
            return False
        copy = self.services.projects.duplicate(self.project.id)
        self.load_project(copy)
        self.status_message.setText(f"Proyecto duplicado como «{copy.name}»")
        return True

    def delete_project(self, *, confirm: bool = True) -> bool:
        if confirm:
            answer = QMessageBox.question(
                self,
                "Eliminar proyecto",
                f"¿Eliminar definitivamente el proyecto «{self.project.name}»?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        if self.project.id is not None:
            self.services.projects.delete(self.project.id)
            self.settings.remove(KEY_LAST_PROJECT)
        self.load_project(self._fresh_project())
        self.status_message.setText("Proyecto eliminado")
        return True

    def maybe_save(self) -> bool:
        """Si hay cambios sin guardar pregunta qué hacer. False = el usuario canceló."""
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Cambios sin guardar",
            f"El proyecto «{self.project.name}» tiene cambios sin guardar. ¿Guardarlos?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    # ------------------------------------------------------------------ estado
    def set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty
        self.setWindowTitle(f"{self.project.name or '(sin nombre)'}[*] — {APP_NAME}")
        self.setWindowModified(dirty)
        self.status_project.setText(f"Proyecto: {self.project.name}")

    def mark_dirty(self) -> None:
        self.set_dirty(True)
        self._validation_timer.start()

    def set_unit(self, unit: Unit) -> None:
        self.units.set_unit(unit)
        self.unit_actions[unit].setChecked(True)
        self.settings.setValue(KEY_UNIT, unit.symbol)
        self._update_plate_status()

    def _on_plate_selected(self, plate_id: int | None) -> None:
        if plate_id != self.project.plate_format_id:
            self.project.plate_format_id = plate_id
            self.mark_dirty()
        self._refresh_context()

    def _on_params_changed(self, params: CuttingParameters) -> None:
        self.project.params = params
        self.mark_dirty()
        self._refresh_context()

    def _refresh_context(self) -> None:
        """Recarga la placa del proyecto y revalida la tabla de piezas."""
        self.plate = None
        if self.project.plate_format_id is not None:
            try:
                self.plate = self.services.plates.get_format(self.project.plate_format_id)
            except LookupError:
                self.project.plate_format_id = None
        self.pieces_widget.set_context(
            self.plate, self.project.params, self.plate_widget.materials()
        )
        self._update_plate_status()
        self._validation_timer.start()

    def _update_plate_status(self) -> None:
        if self.plate is None:
            self.status_plate.setText("Sin placa")
            return
        u = self.units
        dims = f"{u.format(self.plate.width)} × {u.format(self.plate.height)} {u.symbol}"
        self.status_plate.setText(f"Placa: {self.plate.name} ({dims})")

    def run_validation(self) -> None:
        self._validation_timer.stop()
        self.set_issues(self.services.projects.validate(self.project).issues)
        self.update_stale()

    def set_issues(self, issues: list[ValidationIssue]) -> None:
        self.validation_panel.set_issues(issues)
        title = f"Mensajes ({len(issues)})" if issues else "Mensajes"
        self.bottom_tabs.setTabText(self.messages_tab, title)

    # ------------------------------------------------------------------ resultado
    def show_result(self, result: OptimizationResult | None) -> None:
        """Muestra un resultado en el diagrama, las listas y el resumen."""
        self.result = result
        self.result_widget.set_result(result)
        self.diagram_widget.set_result(result)
        self.cut_list_widget.set_result(result)
        self.update_stale()

    def show_message(self, html: str) -> None:
        """Sustituye el resultado por un mensaje (errores, cancelación…)."""
        self.show_result(None)
        self.result_widget.set_message(html)

    @property
    def result_is_stale(self) -> bool:
        return self.result is not None and not self.services.optimization.is_result_current(
            self.project, self.result
        )

    def update_stale(self) -> None:
        """Banner «Resultado desactualizado» si los datos cambiaron desde el cálculo."""
        stale = self.result_is_stale
        self.result_widget.set_stale(stale)
        self.diagram_widget.set_stale(stale)

    def focus_issue(self, issue: ValidationIssue) -> None:
        """Lleva al usuario al campo señalado por un mensaje de validación."""
        if issue.location is not None:
            self.toolbox.setCurrentIndex(PAGE_PIECES)
            self.pieces_widget.focus_cell(*issue.location, issue.field)
            return
        widget = self.parameters_widget.field_widget(issue.field or "")
        if widget is not None:
            self.toolbox.setCurrentIndex(PAGE_PARAMETERS)
            widget.setFocus()
            return
        if issue.code in (IssueCode.NO_PLATE_SELECTED, IssueCode.NON_POSITIVE_DIMENSION):
            self.toolbox.setCurrentIndex(PAGE_PLATE)
            return
        if issue.code is IssueCode.NO_PIECES:
            self.toolbox.setCurrentIndex(PAGE_PIECES)
            return
        if issue.field == "name":
            self.toolbox.setCurrentIndex(PAGE_PROJECT)
            self.project_widget.name_edit.setFocus()

    # ------------------------------------------------------------------ optimización
    @property
    def is_optimizing(self) -> bool:
        return self._worker is not None

    def optimize(self) -> bool:
        """Valida y lanza la optimización en segundo plano. False si no se pudo lanzar."""
        if self.is_optimizing:
            return False
        self.run_validation()
        prepared = self.services.optimization.prepare(self.project)
        if isinstance(prepared, OptimizationOutcome):
            self.set_issues(prepared.report.issues)
            self.bottom_tabs.setCurrentIndex(self.messages_tab)
            self.show_message(
                "Corrija los errores de la lista de <b>Mensajes</b> antes de optimizar."
            )
            self.status_message.setText("Hay errores de validación")
            return False

        self._prepared = prepared
        worker = OptimizationWorker(prepared, time_budget_s=self.time_budget_s)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.cancelled.connect(self._on_cancelled)
        self._worker = worker
        self._set_running(True)
        self.status_message.setText("Optimizando…")
        self.thread_pool.start(worker)
        return True

    def cancel_optimization(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status_message.setText("Cancelando…")

    def _set_running(self, running: bool) -> None:
        self.optimize_button.setEnabled(not running)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(running)
        self.cancel_button.setVisible(running)
        self.cancel_button.setEnabled(running)

    def _end_run(self) -> PreparedOptimization | None:
        prepared, self._prepared, self._worker = self._prepared, None, None
        self._set_running(False)
        return prepared

    def _on_progress(self, fraction: float) -> None:
        self.progress_bar.setValue(int(fraction * 1000))

    def _on_finished(self, result: OptimizationResult) -> None:
        prepared = self._end_run()
        assert prepared is not None
        outcome = self.services.optimization.finish(prepared, result)
        assert outcome.result is not None
        self.show_result(outcome.result)
        self.set_issues(outcome.report.issues)
        if outcome.result.unplaced:
            self.bottom_tabs.setCurrentIndex(self.messages_tab)
        r = outcome.result
        sheets = f"{r.sheets_count} placa{'' if r.sheets_count == 1 else 's'}"
        utilization = f"{r.utilization * 100:.1f} %".replace(".", ",")
        self.status_message.setText(f"{sheets} · {utilization} · {r.strategy} · {r.duration_ms} ms")
        self.optimization_finished.emit(outcome)

    def _on_failed(self, message: str) -> None:
        self._end_run()
        self.show_message(
            "<p><b>La optimización falló por un error interno.</b></p>"
            f"<p>{escape(message)}</p><p>El detalle quedó registrado en el log.</p>"
        )
        self.status_message.setText("La optimización falló")

    def _on_cancelled(self) -> None:
        self._end_run()
        self.show_message("Optimización cancelada.")
        self.status_message.setText("Optimización cancelada")

    # ------------------------------------------------------------------ cierre
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self.maybe_save():
            event.ignore()
            return
        if self._worker is not None:
            self._worker.cancel()
        self.thread_pool.waitForDone()
        self._validation_timer.stop()
        self.save_settings()
        event.accept()
