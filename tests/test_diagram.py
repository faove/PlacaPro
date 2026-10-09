"""Diagrama de placas: la escena se construye solo desde el ``SheetLayout``."""

import pytest
from PySide6.QtCore import QRectF

from models.pieza import GrainDirection, PieceCategory
from models.resultado import OptimizationResult
from models.retazo import OffcutStatus
from optimization.cutting import plan_result
from tests.helpers import params_mm, piece, plate_mm, run
from ui.cutting_diagram_widget import (
    CutLineItem,
    CuttingDiagramWidget,
    DimensionItem,
    OffcutItem,
    PieceItem,
    SheetScene,
    grain_on_sheet,
    legend_entries,
    sheet_tab_title,
)
from ui.theme import CATEGORY_COLORS, OFFCUT_COLOR, WASTE_COLOR
from ui.units_display import UnitsDisplay
from utils.units import Unit

pytestmark = pytest.mark.ui


def multi_sheet_result() -> OptimizationResult:
    """Dos placas o más, varias categorías, una pieza con veta y una que no cabe."""
    specs = [
        piece("Lateral", 2, 600, 700, category=PieceCategory.LATERAL),
        piece("Tapa", 3, 400, 300, category=PieceCategory.TAPA),
        piece("Puerta", 1, 300, 750, category=PieceCategory.PUERTA, grain=GrainDirection.VERTICAL),
        piece("Gigante", 1, 1200, 1200, category=PieceCategory.OTRO),
    ]
    result = run(specs, plate_mm(1000, 800), params_mm())
    return plan_result(result, None)


@pytest.fixture(scope="module")
def result():
    return multi_sheet_result()


@pytest.fixture
def units(qapp):
    return UnitsDisplay(Unit.MM)


def test_result_fixture_is_rich_enough(result):
    assert result.sheets_count >= 2
    assert len(result.unplaced) == 1
    assert any(o.status is OffcutStatus.WASTE for s in result.sheets for o in s.offcuts)


def test_piece_items_match_placements_exactly(result, units):
    for sheet in result.sheets:
        scene = SheetScene(sheet, units)
        pieces = [i for i in scene.items() if isinstance(i, PieceItem)]
        assert len(pieces) == len(sheet.placements)
        for item, placement in zip(scene.piece_items, sheet.placements, strict=True):
            assert item.placement is placement
            assert item.rect() == QRectF(
                placement.x, placement.y, placement.width, placement.height
            )
            assert (
                item.brush().color().name().upper()
                == CATEGORY_COLORS[placement.piece.spec.category].upper()
            )


def test_every_rectangle_has_a_model_object_behind(result, units):
    """Regla de oro: placa, colocaciones, retazos y desperdicio; nada decorativo."""
    for sheet in result.sheets:
        scene = SheetScene(sheet, units)
        offcuts = [i for i in scene.items() if isinstance(i, OffcutItem)]
        assert sorted(map(id, (i.offcut for i in offcuts))) == sorted(map(id, sheet.offcuts))
        for item in offcuts:
            o = item.offcut
            assert item.rect() == QRectF(o.x, o.y, o.width, o.height)
            expected = WASTE_COLOR if o.status is OffcutStatus.WASTE else OFFCUT_COLOR
            assert item.brush().color().name().upper() == expected.upper()
        assert scene.plate_item.rect() == QRectF(0, 0, sheet.width, sheet.height)
        known = {
            scene.plate_item,
            scene.margin_item,
            *scene.piece_items,
            *offcuts,
            *scene.cut_items.values(),
            *scene.dimension_items,
        }
        assert set(scene.items()) <= known


def test_cut_layer_follows_cut_plan(result, units):
    sheet = result.sheets[0]
    scene = SheetScene(sheet, units)
    assert sheet.cut_plan is not None
    assert sorted(scene.cut_items) == [c.order for c in sheet.cut_plan.cuts]
    assert all(isinstance(i, CutLineItem) and not i.isVisible() for i in scene.cut_items.values())
    scene.set_cuts_visible(True)
    scene.set_dimensions_visible(True)
    assert all(i.isVisible() for i in scene.cut_items.values())
    assert all(isinstance(i, DimensionItem) and i.isVisible() for i in scene.dimension_items)
    cut = sheet.cut_plan.cuts[-1]
    rect = scene.cut_items[cut.order].rect()
    if cut.orientation.value == "horizontal":
        assert rect == QRectF(cut.start, cut.position, cut.length, cut.kerf)
    else:
        assert rect == QRectF(cut.position, cut.start, cut.kerf, cut.length)


def test_labels_and_tooltips_follow_units(result, units):
    sheet = result.sheets[0]
    scene = SheetScene(sheet, units)
    item = scene.piece_items[0]
    p = item.placement
    assert item.lines()[0].startswith(p.piece.label)
    assert item.lines()[1] == f"{units.format(p.width)} × {units.format(p.height)}"
    assert f"X = {units.format(p.x)} mm" in item.toolTip()
    units.set_unit(Unit.CM)
    scene.refresh_units()
    assert item.lines()[1] == f"{units.format(p.width)} × {units.format(p.height)}"
    assert f"X = {units.format(p.x)} cm" in item.toolTip()


def test_rotation_and_grain_marks(result, units):
    for sheet in result.sheets:
        for item in SheetScene(sheet, units).piece_items:
            p = item.placement
            assert ("⟲" in item.lines()[0]) == p.rotated
            if p.piece.spec.grain is GrainDirection.VERTICAL:
                expected = "↔" if p.rotated else "↕"
                assert expected in item.lines()[0]
                assert grain_on_sheet(p) is not None
            else:
                assert grain_on_sheet(p) is None


def test_legend_only_present_categories(result):
    entries = legend_entries(result)
    names = [name for name, _ in entries]
    assert names[:3] == ["Lateral", "Tapa", "Puerta"]
    assert "Desperdicio" in names
    assert "Estante" not in names and "Otro" not in names  # «Gigante» no se colocó
    assert legend_entries(None) == []


def test_widget_tabs_and_layers(qtbot, result, units):
    widget = CuttingDiagramWidget(units)
    qtbot.addWidget(widget)
    widget.resize(800, 600)
    widget.show()
    widget.set_result(result)
    assert widget.tabs.count() == result.sheets_count
    assert widget.tabs.tabText(0) == sheet_tab_title(result.sheets[0])
    assert widget.tabs.tabText(0).startswith("Placa 1 — ") and widget.tabs.tabText(0).endswith("%")
    assert "Lateral" in widget.legend.text()

    widget.cuts_check.setChecked(True)
    assert all(i.isVisible() for s in widget.scenes for i in s.cut_items.values())

    view = widget.current_view()
    fitted = view.current_scale()
    widget.zoom_in_button.click()
    assert view.current_scale() == pytest.approx(fitted * 1.15) and not view.auto_fit
    widget.fit_button.click()
    assert view.auto_fit and view.current_scale() == pytest.approx(fitted)

    widget.set_result(None)
    assert widget.tabs.count() == 0 and widget.stack.currentWidget() is widget.placeholder


def test_select_piece_switches_tab_without_emitting(qtbot, result, units):
    widget = CuttingDiagramWidget(units)
    qtbot.addWidget(widget)
    widget.set_result(result)
    last = result.sheets[-1]
    with qtbot.assertNotEmitted(widget.piece_selected):
        assert widget.select_piece(last.index, 0)
    assert widget.tabs.currentIndex() == len(result.sheets) - 1
    assert widget.selected_piece() == (last.index, 0)
    assert not widget.select_piece(99, 0)

    # Selección hecha por el usuario en la escena ⇒ señal.
    scene = widget.scenes[0]
    with qtbot.waitSignal(widget.piece_selected) as blocker:
        scene.clearSelection()
        scene.piece_items[1].setSelected(True)
    assert blocker.args == [result.sheets[0].index, 1]


def test_select_cut_turns_cut_layer_on(qtbot, result, units):
    widget = CuttingDiagramWidget(units)
    qtbot.addWidget(widget)
    widget.set_result(result)
    assert not widget.cuts_check.isChecked()
    assert widget.select_cut(0, 1)
    assert widget.cuts_check.isChecked()
    assert widget.scenes[0].cut_items[1].isSelected()
