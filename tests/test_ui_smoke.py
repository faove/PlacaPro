"""Tests de humo de la ventana principal (pytest-qt, offscreen) contra SQLite en memoria."""

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMessageBox

from app import create_main_window
from database.database import Database
from database.seed import DEMO_PROJECT_NAME
from models.validation import IssueCode
from ui.main_window import KEY_LAST_PROJECT, KEY_UNIT, PAGE_PARAMETERS, PAGE_PIECES, MainWindow
from ui.pieces_widget import Column
from ui.workers import OptimizationWorker
from utils.units import Unit, mm_to_internal

pytestmark = pytest.mark.ui

EDIT = Qt.ItemDataRole.EditRole


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def window(qtbot, settings):
    db = Database(":memory:")
    win = create_main_window(db, settings, time_budget_s=2)
    # Sin qtbot.addWidget: qtbot cerraría la ventana antes de este teardown y el aviso
    # de cambios sin guardar (modal) bloquearía el test.
    win.show()
    yield win
    win.dirty = False
    win.close()
    win.deleteLater()
    db.close()


def piece_index(win: MainWindow, row: int, column: Column):
    return win.pieces_widget.model.index(row, column)


def test_window_opens_with_demo(window):
    assert window.isVisible()
    assert window.project.name == DEMO_PROJECT_NAME
    assert window.windowTitle() == f"{DEMO_PROJECT_NAME}[*] — PlacaPro"
    assert not window.isWindowModified()
    assert window.pieces_widget.model.rowCount() == 5
    assert window.plate_widget.selected_plate_id() == window.project.plate_format_id
    assert window.plate is not None and window.plate.width == mm_to_internal(1830)
    assert window.validation_panel.issues == []


def test_editing_a_piece_marks_unsaved(window):
    model = window.pieces_widget.model
    assert model.setData(piece_index(window, 0, Column.WIDTH), "410", EDIT)
    assert window.dirty and window.isWindowModified()
    assert window.project.furniture[0].pieces[0].width == mm_to_internal(410)
    assert window.save()
    assert not window.isWindowModified()
    reopened = window.services.projects.open(window.project.id)
    assert reopened.furniture[0].pieces[0].width == mm_to_internal(410)


def test_optimize_emits_finished_with_result(window, qtbot):
    with qtbot.waitSignal(window.optimization_finished, timeout=30_000) as blocker:
        assert window.optimize()
        assert window.is_optimizing and not window.optimize_button.isEnabled()
    outcome = blocker.args[0]
    assert outcome.ok and outcome.result.pieces_count == 7
    assert outcome.result.id is not None  # proyecto guardado ⇒ resultado persistido
    assert not window.is_optimizing and window.optimize_button.isEnabled()
    assert "Aprovechamiento" in window.result_widget.toPlainText()
    assert window.services.optimization.latest_result(window.project.id).id == outcome.result.id


def test_validation_errors_block_and_issue_focuses_cell(window, qtbot):
    model = window.pieces_widget.model
    model.setData(piece_index(window, 1, Column.WIDTH), "5000", EDIT)
    with qtbot.assertNotEmitted(window.optimization_finished, wait=100):
        assert not window.optimize()
    issues = window.validation_panel.issues
    issue = next(i for i in issues if i.code is IssueCode.PIECE_LARGER_THAN_PLATE)
    assert issue.location == (0, 1)
    assert "Corrija" in window.result_widget.toPlainText()

    window.toolbox.setCurrentIndex(0)
    window.validation_panel.list.itemClicked.emit(window.validation_panel.list.item(0))
    assert window.toolbox.currentIndex() == PAGE_PIECES
    assert window.pieces_widget.table.currentIndex().row() == 1


def test_parameter_issue_focuses_parameters(window):
    window.parameters_widget.edits["kerf"].setText("20")
    window.parameters_widget.edits["kerf"].editingFinished.emit()
    assert window.project.params.kerf == mm_to_internal(20) and window.dirty
    window.run_validation()
    issue = next(i for i in window.validation_panel.issues if i.code is IssueCode.INVALID_KERF)
    window.focus_issue(issue)
    assert window.toolbox.currentIndex() == PAGE_PARAMETERS


def test_cancel_worker_emits_cancelled(window, qtbot):
    prepared = window.services.optimization.prepare(window.project)
    worker = OptimizationWorker(prepared)
    worker.cancel()
    with qtbot.waitSignal(worker.signals.cancelled):
        worker.run()


def test_cancel_from_window(window, qtbot):
    window.optimize()
    window.cancel_optimization()
    qtbot.waitUntil(lambda: not window.is_optimizing, timeout=30_000)
    # Según el momento, el hilo termina antes o se cancela; la UI vuelve a estar lista.
    assert window.optimize_button.isEnabled() and not window.progress_bar.isVisible()


def test_unit_switch(window, settings):
    window.set_unit(Unit.CM)
    assert piece_index(window, 0, Column.WIDTH).data() == "40"
    assert window.parameters_widget.edits["kerf"].text() == "0,32"
    assert "183 × 282 cm" in window.status_plate.text()
    assert settings.value(KEY_UNIT) == "cm"


def test_file_operations(window, monkeypatch):
    projects = window.services.projects
    demo_id = window.project.id

    assert window.new_project()
    assert window.project.id is None and window.pieces_widget.model.rowCount() == 0
    assert window.project.plate_format_id is not None
    window.project_widget.name_edit.setText("Placard")
    window.project_widget.name_edit.textEdited.emit("Placard")
    window.pieces_widget.model.add_piece()
    assert window.dirty
    assert window.save()
    placard_id = window.project.id
    assert {p.name for p in projects.list_projects()} == {DEMO_PROJECT_NAME, "Placard"}

    assert window.save_as("Placard grande")
    assert window.project.id not in (None, placard_id) and window.project.name == "Placard grande"

    assert window.duplicate_project()
    assert window.project.name == "Placard grande (copia)"
    copy_id = window.project.id

    assert window.delete_project(confirm=False)
    assert not projects.projects.exists(copy_id) and window.project.id is None

    assert window.open_project(demo_id)
    assert window.project.name == DEMO_PROJECT_NAME
    assert len(projects.list_projects()) == 3

    # Con cambios sin guardar se pregunta; «Cancelar» mantiene el proyecto abierto.
    window.pieces_widget.model.add_piece()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    assert not window.open_project(placard_id)
    assert window.project.id == demo_id and window.dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
    assert window.open_project(placard_id)
    assert window.project.name == "Placard" and not window.dirty
    assert projects.open(demo_id).total_piece_count == 7


def test_plate_selection_and_save(window):
    plate_widget = window.plate_widget
    other = next(p for p in window.services.plates.list_formats() if p.width_mm == 2440)
    plate_widget.plate_list.setCurrentRow(
        next(
            r
            for r in range(plate_widget.plate_list.count())
            if plate_widget.plate_list.item(r).data(Qt.ItemDataRole.UserRole) == other.id
        )
    )
    assert window.project.plate_format_id == other.id and window.dirty
    plate_widget.stock_spin.setValue(4)
    plate_widget.color_edit.setText("Roble")
    assert plate_widget.save_plate() is not None
    assert window.services.inventory.available_plates(other.id) == 4
    assert window.services.plates.get_format(other.id).color == "Roble"

    plate_widget.new_plate()
    plate_widget.name_edit.setText("")
    assert plate_widget.save_plate() is None
    assert "nombre" in plate_widget.error_label.text()

    plate_widget.delete_plate(confirm=False)  # sin selección: no hace nada
    plate_widget.set_selected_plate(other.id)
    plate_widget.delete_plate(confirm=False)
    assert window.project.plate_format_id is None
    window.run_validation()
    assert IssueCode.NO_PLATE_SELECTED in {i.code for i in window.validation_panel.issues}


def test_furniture_management(window):
    pw = window.project_widget
    pw.add_furniture()
    assert len(window.project.furniture) == 2
    assert window.pieces_widget.furniture_combo.count() == 2
    assert window.pieces_widget.model.rowCount() == 0  # se muestra el mueble nuevo
    pw.furniture_list.item(1).setText("Cajonera")
    assert window.project.furniture[1].name == "Cajonera"
    assert window.pieces_widget.furniture_combo.itemText(1) == "Cajonera"
    pw.select_furniture(0)
    assert window.pieces_widget.model.rowCount() == 5
    pw.select_furniture(1)
    pw.remove_current_furniture(confirm=False)
    assert len(window.project.furniture) == 1 and window.pieces_widget.model.rowCount() == 5


def test_settings_persist_last_project(qtbot, settings, tmp_path):
    db = Database(tmp_path / "p.db")
    win = create_main_window(db, settings)
    qtbot.addWidget(win)
    win.save_as("Otro")
    other_id = win.project.id
    win.set_unit(Unit.M)
    win.close()
    assert int(settings.value(KEY_LAST_PROJECT)) == other_id

    again = create_main_window(db, settings)
    qtbot.addWidget(again)
    assert again.project.id == other_id and again.units.unit is Unit.M
    again.close()
    db.close()
