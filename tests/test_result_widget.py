"""Panel de resultado y lista/secuencia de cortes."""

import pytest
from PySide6.QtCore import Qt

from tests.test_diagram import multi_sheet_result
from ui.cut_list_widget import (
    TAB_CUT_LIST,
    TAB_SEQUENCE,
    CutListWidget,
    PieceColumn,
    SequenceColumn,
)
from ui.result_widget import ResultWidget, result_details, result_kpis
from ui.units_display import UnitsDisplay
from utils.units import Unit, format_area_m2

pytestmark = pytest.mark.ui


@pytest.fixture(scope="module")
def result():
    return multi_sheet_result()


@pytest.fixture
def units(qapp):
    return UnitsDisplay(Unit.MM)


def test_kpis_match_result_metrics(qtbot, result, units):
    widget = ResultWidget(units)
    qtbot.addWidget(widget)
    widget.set_result(result)
    kpis = widget.kpi_values()
    assert kpis == result_kpis(result)
    assert kpis["Placas necesarias"] == str(result.sheets_count)
    assert kpis["Área total"] == format_area_m2(result.total_area)
    assert kpis["Área utilizada"] == format_area_m2(result.used_area)
    assert kpis["Desperdicio"] == format_area_m2(result.waste_area)
    assert kpis["Aprovechamiento"] == f"{result.utilization * 100:.1f} %".replace(".", ",")
    assert kpis["Nº de piezas"] == str(result.pieces_count)
    details = result_details(result)
    assert details["Estrategia"] == result.strategy
    assert str(result.lower_bound) in details["Cota inferior"]


def test_sheet_table_and_unplaced_warning(qtbot, result, units):
    widget = ResultWidget(units)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_result(result)
    table = widget.sheet_table
    assert table.rowCount() == result.sheets_count
    for r, sheet in enumerate(result.sheets):
        assert table.item(r, 1).text() == sheet.source.label
        assert table.item(r, 3).text() == str(len(sheet.placements))
        assert table.item(r, 5).text() == format_area_m2(sheet.used_area)
        assert table.item(r, 6).text() == format_area_m2(sheet.waste_area)
    assert widget.unplaced_banner.isVisible()
    assert "Gigante" in widget.unplaced_banner.text()

    with qtbot.waitSignal(widget.sheet_activated) as blocker:
        table.cellClicked.emit(1, 0)
    assert blocker.args == [result.sheets[1].index]

    units.set_unit(Unit.CM)
    sheet = result.sheets[0]
    assert table.item(0, 2).text() == f"{units.format(sheet.width)} × {units.format(sheet.height)}"
    assert table.horizontalHeaderItem(2).text() == "Medidas (cm)"


def test_message_and_stale(qtbot, result, units):
    widget = ResultWidget(units)
    qtbot.addWidget(widget)
    widget.show()
    assert "OPTIMIZAR" in widget.message_text()
    widget.set_stale(True)
    assert not widget.stale_banner.isVisible()  # sin resultado no hay banner
    widget.set_result(result)
    widget.set_stale(True)
    assert widget.stale_banner.isVisible()
    widget.set_message("Optimización cancelada.")
    assert widget.result is None and not widget.stale_banner.isVisible()
    assert widget.message_text() == "Optimización cancelada."


def test_cut_list_rows_filter_and_sort(qtbot, result, units):
    widget = CutListWidget(units)
    qtbot.addWidget(widget)
    widget.set_result(result)
    model, proxy = widget.piece_model, widget.piece_proxy
    assert model.rowCount() == result.pieces_count
    first = result.sheets[0].placements[0]
    assert model.index(0, PieceColumn.PIECE).data() == first.piece.label
    assert model.index(0, PieceColumn.X).data() == units.format(first.x)
    assert model.headerData(PieceColumn.WIDTH, Qt.Orientation.Horizontal) == "Ancho (mm)"

    widget.set_sheet_filter(1)
    assert proxy.rowCount() == len(result.sheets[1].placements)
    widget.set_sheet_filter(-1)
    assert proxy.rowCount() == result.pieces_count

    # Orden numérico (no alfabético) por ancho.
    widget.piece_table.sortByColumn(PieceColumn.WIDTH, Qt.SortOrder.AscendingOrder)
    widths = [
        proxy.index(r, PieceColumn.WIDTH).data(Qt.ItemDataRole.UserRole + 1)
        for r in range(proxy.rowCount())
    ]
    assert widths == sorted(widths)

    units.set_unit(Unit.CM)
    assert model.index(0, PieceColumn.X).data() == units.format(first.x)
    assert model.headerData(PieceColumn.WIDTH, Qt.Orientation.Horizontal) == "Ancho (cm)"


def test_sequence_rows(qtbot, result, units):
    widget = CutListWidget(units)
    qtbot.addWidget(widget)
    widget.set_result(result)
    seq = widget.sequence_model
    cuts = [(s.index, c) for s in result.sheets for c in s.cut_plan.cuts]
    assert seq.rowCount() == len(cuts)
    sheet_index, cut = cuts[0]
    assert seq.index(0, SequenceColumn.CUT).data() == f"CORTE {cut.order}"
    assert seq.index(0, SequenceColumn.FENCE).data() == units.format(cut.fence_distance)
    assert seq.index(0, SequenceColumn.LENGTH).data() == units.format(cut.length)
    assert seq.index(0, SequenceColumn.LEVEL).data() == ("0 · refilado" if cut.is_trim else "1")


def test_cut_list_selection_signals(qtbot, result, units):
    widget = CutListWidget(units)
    qtbot.addWidget(widget)
    widget.set_result(result)
    last = result.sheets[-1]

    with qtbot.assertNotEmitted(widget.piece_selected):
        assert widget.select_piece(last.index, 0)
    assert widget.currentIndex() == TAB_CUT_LIST
    selected = widget.piece_table.selectionModel().selectedRows()
    source = widget.piece_proxy.mapToSource(selected[0])
    assert widget.piece_model.rows[source.row()].sheet_index == last.index

    widget.set_sheet_filter(0)  # filtrada otra placa: seleccionar la cambia
    assert widget.select_cut(last.index, 2)
    assert widget.currentIndex() == TAB_SEQUENCE
    assert widget.sequence_proxy.sheet_index == last.index

    with qtbot.waitSignal(widget.piece_selected) as blocker:
        widget.piece_table.selectRow(0)
    assert (
        blocker.args[0]
        == widget.piece_model.rows[
            widget.piece_proxy.mapToSource(widget.piece_proxy.index(0, 0)).row()
        ].sheet_index
    )
