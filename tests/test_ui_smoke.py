"""Tests de humo de la ventana principal (pytest-qt, offscreen) contra SQLite en memoria."""

from dataclasses import replace

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence
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
    win = create_main_window(db, settings, time_budget_s=2, optimize_demo=False)
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
    assert window.result_widget.kpi_values()["Aprovechamiento"].endswith("%")
    assert window.services.optimization.latest_result(window.project.id).id == outcome.result.id


def test_validation_errors_block_and_issue_focuses_cell(window, qtbot):
    model = window.pieces_widget.model
    model.setData(piece_index(window, 1, Column.WIDTH), "5000", EDIT)
    with qtbot.assertNotEmitted(window.optimization_finished, wait=100):
        assert not window.optimize()
    issues = window.validation_panel.issues
    issue = next(i for i in issues if i.code is IssueCode.PIECE_LARGER_THAN_PLATE)
    assert issue.location == (0, 1)
    assert "Corrija" in window.result_widget.message_text()

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
    win = create_main_window(db, settings, optimize_demo=False)
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


def optimize_and_wait(window, qtbot):
    with qtbot.waitSignal(window.optimization_finished, timeout=30_000) as blocker:
        assert window.optimize()
    return blocker.args[0].result


def test_optimize_fills_diagram_and_cut_list(window, qtbot):
    result = optimize_and_wait(window, qtbot)
    diagram = window.diagram_widget
    assert diagram.tabs.count() == result.sheets_count
    assert sum(len(s.piece_items) for s in diagram.scenes) == result.pieces_count
    assert window.cut_list_widget.piece_model.rowCount() == result.pieces_count
    assert window.result_widget.kpi_values()["Nº de piezas"] == str(result.pieces_count)
    assert not window.diagram_widget.stale_banner.isVisible()


def test_selection_is_synchronized(window, qtbot):
    result = optimize_and_wait(window, qtbot)
    sheet = result.sheets[0]
    cut_list = window.cut_list_widget

    # Diagrama → tabla.
    scene = window.diagram_widget.scenes[0]
    scene.clearSelection()
    scene.piece_items[2].setSelected(True)
    row = cut_list.piece_table.selectionModel().selectedRows()[0]
    selected = cut_list.piece_model.rows[cut_list.piece_proxy.mapToSource(row).row()]
    assert (selected.sheet_index, selected.placement_index) == (sheet.index, 2)

    # Tabla → diagrama.
    r = cut_list.piece_model.row_of(sheet.index, 4)
    cut_list.piece_table.selectRow(
        cut_list.piece_proxy.mapFromSource(cut_list.piece_model.index(r, 0)).row()
    )
    assert window.diagram_widget.selected_piece() == (sheet.index, 4)

    # Secuencia → corte resaltado en el diagrama (capa activada).
    order = sheet.cut_plan.cuts[-1].order
    r = cut_list.sequence_model.row_of(sheet.index, order)
    cut_list.setCurrentIndex(1)
    cut_list.sequence_table.selectRow(
        cut_list.sequence_proxy.mapFromSource(cut_list.sequence_model.index(r, 0)).row()
    )
    assert window.diagram_widget.cuts_check.isChecked()
    assert window.diagram_widget.scenes[0].cut_items[order].isSelected()


def test_reopen_shows_last_result_and_stale_banner(window, qtbot):
    result = optimize_and_wait(window, qtbot)
    project_id = window.project.id
    assert window.new_project()
    assert window.diagram_widget.tabs.count() == 0

    assert window.open_project(project_id)
    assert window.result is not None and window.result.id == result.id
    assert window.diagram_widget.tabs.count() == result.sheets_count
    assert not window.result_is_stale and not window.result_widget.stale_banner.isVisible()

    # Cambiar una medida deja el resultado desactualizado; volver atrás lo restablece.
    model = window.pieces_widget.model
    original = piece_index(window, 0, Column.WIDTH).data()
    model.setData(piece_index(window, 0, Column.WIDTH), "410", EDIT)
    window.run_validation()
    assert window.result_is_stale
    assert window.result_widget.stale_banner.isVisible()
    assert window.diagram_widget.stale_banner.isVisible()
    model.setData(piece_index(window, 0, Column.WIDTH), original, EDIT)
    window.run_validation()
    assert not window.result_is_stale and not window.diagram_widget.stale_banner.isVisible()

    # Renombrar el proyecto no invalida el resultado; cambiar el kerf sí.
    window.project.name = "Otro nombre"
    assert not window.result_is_stale
    window.parameters_widget.edits["kerf"].setText("4")
    window.parameters_widget.edits["kerf"].editingFinished.emit()
    window.run_validation()
    assert window.result_is_stale
    # Al guardar y reabrir con datos cambiados, el banner sigue.
    assert window.save()
    assert window.open_project(project_id)
    assert window.result_is_stale and window.result_widget.stale_banner.isVisible()


def test_validation_error_switches_to_messages_tab(window):
    window.pieces_widget.model.setData(piece_index(window, 1, Column.WIDTH), "5000", EDIT)
    assert not window.optimize()
    assert window.bottom_tabs.currentIndex() == window.messages_tab
    assert window.bottom_tabs.tabText(window.messages_tab).startswith("Mensajes (")


def test_export_menu_and_export(window, qtbot, tmp_path):
    assert list(window.export_actions)[:3] == ["pdf", "csv", "svg"]
    window.show_result(None)
    assert not window.export_actions["pdf"].isEnabled()
    assert window.export("pdf", tmp_path / "x.pdf") == []

    optimize_and_wait(window, qtbot)
    assert window.export_actions["pdf"].isEnabled()
    [pdf] = window.export("pdf", tmp_path / "demo.pdf")
    assert pdf.exists() and "demo.pdf" in window.status_message.text()
    window.set_unit(Unit.CM)
    _, cuts = window.export("csv", tmp_path / "demo.csv")
    assert "Ancho (cm)" in cuts.read_text(encoding="utf-8-sig")


def test_confirm_plan_discounts_stock(window, qtbot):
    plate_id = window.project.plate_format_id
    inventory = window.services.inventory
    inventory.set_available_plates(plate_id, 2)
    window.parameters_widget.stock_check.setChecked(True)
    assert window.save()
    result = optimize_and_wait(window, qtbot)
    assert result.stock_plates_used() == {plate_id: 1}
    assert window.result_widget.confirm_button.isEnabled()
    assert "1 placa del inventario" in window.result_widget.confirm_label.text()

    assert window.confirm_plan(confirm=False)
    assert inventory.available_plates(plate_id) == 1
    assert window.result.is_confirmed
    assert not window.result_widget.confirm_button.isEnabled()
    assert "confirmado" in window.result_widget.confirm_label.text()
    assert "stock: 1" in window.plate_widget.plate_list.currentItem().text()
    assert not window.confirm_plan(confirm=False)  # una sola vez

    # Reabrir mantiene el estado confirmado.
    assert window.open_project(window.project.id, ask_save=False)
    assert window.result.is_confirmed and not window.result_widget.confirm_button.isEnabled()


def test_confirm_disabled_when_stale_or_unsaved(window, qtbot):
    optimize_and_wait(window, qtbot)
    window.pieces_widget.model.setData(piece_index(window, 0, Column.WIDTH), "410", EDIT)
    window.run_validation()
    assert not window.result_widget.confirm_button.isEnabled()
    assert not window.confirm_plan(confirm=False)

    window.dirty = False
    assert window.new_project()
    window.pieces_widget.model.add_piece()
    model = window.pieces_widget.model
    model.setData(model.index(0, Column.WIDTH), "300", EDIT)
    model.setData(model.index(0, Column.HEIGHT), "300", EDIT)
    optimize_and_wait(window, qtbot)
    assert window.result.id is None
    assert "Guarde el proyecto" in window.result_widget.confirm_label.text()


def test_offcuts_tab_saves_consumes_and_deletes(window, qtbot):
    result = optimize_and_wait(window, qtbot)
    offcuts = window.offcuts_widget
    reusable = [o for s in result.sheets for o in s.offcuts if o.status.value == "reusable"]
    assert offcuts.result_table.rowCount() == len(reusable) > 0
    assert offcuts.save_all_button.isEnabled()

    stored = offcuts.save_to_stock(selected_only=False)
    assert len(stored) == len(reusable)
    assert offcuts.stock_table.rowCount() == len(reusable)
    assert not offcuts.save_all_button.isEnabled()  # ya están en stock
    assert all(
        o.status.value == "in_stock" for s in window.result.sheets for o in s.offcuts if o.label
    )

    window.show_offcuts()
    assert window.bottom_tabs.currentIndex() == window.offcuts_tab
    offcuts.stock_table.selectRow(0)
    assert offcuts.mark_selected_consumed() == 1
    assert offcuts.stock_table.rowCount() == len(reusable) - 1
    if offcuts.stock_table.rowCount():
        offcuts.stock_table.selectRow(0)
        assert offcuts.delete_selected(confirm=False) == 1
    assert window.services.inventory.available_offcuts() == []


def test_inventory_dialog_edits_stock(window):
    plate_id = window.project.plate_format_id
    dialog = window.open_inventory()
    assert dialog.table.rowCount() == len(window.services.plates.list_formats())
    dialog.set_quantity(plate_id, 5)
    assert dialog.changes() == {plate_id: 5}
    dialog.accept()
    assert window.services.inventory.available_plates(plate_id) == 5
    assert "stock: 5" in window.plate_widget.plate_list.currentItem().text()

    dialog = window.open_inventory()
    dialog.set_quantity(plate_id, 1)
    dialog.reject()
    assert window.services.inventory.available_plates(plate_id) == 5


def test_errors_disable_optimize_button_warnings_do_not(window, qtbot):
    model = window.pieces_widget.model
    assert window.optimize_button.isEnabled() and window.action_optimize.isEnabled()
    model.setData(piece_index(window, 1, Column.WIDTH), "5000", EDIT)
    qtbot.waitUntil(lambda: not window.optimize_button.isEnabled())
    assert not window.action_optimize.isEnabled()
    assert "Corrija" in window.optimize_button.toolTip()
    model.setData(piece_index(window, 1, Column.WIDTH), "564", EDIT)
    qtbot.waitUntil(window.optimize_button.isEnabled)
    # una advertencia (material distinto) no bloquea
    window.project.furniture[0].pieces[0] = replace(
        window.project.furniture[0].pieces[0], material_id=999
    )
    window.run_validation()
    assert window.validation_panel.issues and window.optimize_button.isEnabled()


def test_shortcuts_and_toolbar(window):
    shortcuts = {k.toString() for k in window.action_optimize.shortcuts()}
    assert {"Ctrl+Return", "Ctrl+Enter", "F5"} <= shortcuts
    assert window.action_export_default is window.export_actions["pdf"]
    assert window.action_export_default.shortcut().toString() == "Ctrl+E"
    assert window.action_save_as.shortcut() == QKeySequence("Ctrl+Shift+S")
    toolbar_actions = window.toolbar.actions()
    for action in (window.action_new, window.action_open, window.action_save):
        assert action in toolbar_actions and not action.icon().isNull()
    assert window.action_optimize in toolbar_actions


def test_optimize_action_runs_and_toggles_cancel(window, qtbot):
    assert not window.action_cancel.isEnabled()
    with qtbot.waitSignal(window.optimization_finished, timeout=30_000):
        window.action_optimize.trigger()
        assert window.action_cancel.isEnabled() and not window.action_optimize.isEnabled()
    assert not window.action_cancel.isEnabled() and window.action_optimize.isEnabled()
    assert window.action_confirm.isEnabled()


def test_parameter_and_grain_tooltips(window):
    params = window.parameters_widget
    assert "513,2" in params.edits["kerf"].toolTip()
    assert "1810 × 2800" in params.edits["edge_margin"].toolTip()
    assert "veta" in params.rotation_check.toolTip()
    assert "Veta" in window.plate_widget.grain_combo.toolTip()
    header = window.pieces_widget.model.headerData(
        Column.GRAIN, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole
    )
    assert "Vertical" in header


def test_worker_throttles_progress(window):
    prepared = window.services.optimization.prepare(window.project)
    worker = OptimizationWorker(prepared)
    emitted = []
    worker.signals.progress.connect(emitted.append)
    for i in range(1000):
        worker._on_progress(i / 1000, None)
    worker._on_progress(1.0, None)
    assert emitted[0] == 0 and emitted[-1] == 1.0
    assert len(emitted) < 10
