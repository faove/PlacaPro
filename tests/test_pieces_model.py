import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QStyleOptionViewItem, QWidget

from models.parametros import CuttingParameters
from models.pieza import GrainDirection, PieceCategory, PieceSpec
from models.placa import PlateFormat, PlateGrain
from models.proyecto import Furniture
from ui.pieces_widget import Column, PiecesDelegate, PiecesTableModel
from ui.theme import ERROR_BACKGROUND
from ui.units_display import UnitsDisplay
from utils.units import Unit, mm_to_internal

pytestmark = pytest.mark.ui

EDIT = Qt.ItemDataRole.EditRole
PLATE = PlateFormat.from_mm("Placa", 1830, 2820, 18, grain=PlateGrain.NONE, id=1)


@pytest.fixture
def setup(qtbot):
    units = UnitsDisplay()
    model = PiecesTableModel(units)
    furniture = Furniture(
        "Mesita",
        [
            PieceSpec.from_mm("Lateral", 2, 400, 600, 18, category=PieceCategory.LATERAL),
            PieceSpec.from_mm("Tapa", 1, 564, 400, 18),
        ],
    )
    model.set_furniture(furniture, 0)
    model.set_context(PLATE, CuttingParameters(), {7: "Melamina"})
    return units, model, furniture


def test_display_and_headers_follow_unit(setup):
    units, model, _ = setup
    assert model.rowCount() == 2 and model.columnCount() == len(Column)
    assert model.index(0, Column.WIDTH).data() == "400"
    assert model.headerData(Column.WIDTH, Qt.Orientation.Horizontal) == "Ancho (mm)"
    assert model.index(0, Column.CATEGORY).data() == "Lateral"
    assert model.index(0, Column.MATERIAL).data() == "Según placa"
    units.set_unit(Unit.CM)
    assert model.index(0, Column.WIDTH).data() == "40"
    assert model.headerData(Column.WIDTH, Qt.Orientation.Horizontal) == "Ancho (cm)"


def test_edit_cells_updates_furniture(setup, qtbot):
    units, model, furniture = setup
    units.set_unit(Unit.CM)
    with qtbot.waitSignal(model.pieces_changed):
        assert model.setData(model.index(0, Column.WIDTH), "45,5", EDIT)
    assert furniture.pieces[0].width == mm_to_internal(455)
    assert model.setData(model.index(0, Column.NAME), "  Lateral izq  ", EDIT)
    assert model.setData(model.index(0, Column.QUANTITY), 3, EDIT)
    assert model.setData(model.index(0, Column.CATEGORY), "puerta", EDIT)
    assert model.setData(model.index(0, Column.GRAIN), "vertical", EDIT)
    assert model.setData(model.index(0, Column.MATERIAL), 7, EDIT)
    spec = furniture.pieces[0]
    assert (spec.name, spec.quantity, spec.category, spec.grain, spec.material_id) == (
        "Lateral izq",
        3,
        PieceCategory.PUERTA,
        GrainDirection.VERTICAL,
        7,
    )
    assert model.index(0, Column.MATERIAL).data() == "Melamina"

    check = Qt.ItemDataRole.CheckStateRole
    assert model.index(0, Column.ROTATE).data(check) == Qt.CheckState.Checked
    assert model.setData(model.index(0, Column.ROTATE), Qt.CheckState.Unchecked.value, check)
    assert model.setData(model.index(0, Column.FIXED), Qt.CheckState.Checked.value, check)
    assert not furniture.pieces[0].can_rotate and furniture.pieces[0].fixed_orientation
    assert model.flags(model.index(0, Column.ROTATE)) & Qt.ItemFlag.ItemIsUserCheckable
    assert not model.flags(model.index(0, Column.ROTATE)) & Qt.ItemFlag.ItemIsEditable


def test_invalid_input_is_rejected_and_marked(setup, qtbot):
    _, model, furniture = setup
    index = model.index(0, Column.HEIGHT)
    with qtbot.assertNotEmitted(model.pieces_changed):
        assert not model.setData(index, "60,05", EDIT)
        assert not model.setData(index, "abc", EDIT)
    assert furniture.pieces[0].height == mm_to_internal(600)
    assert index.data(Qt.ItemDataRole.BackgroundRole) == QColor(ERROR_BACKGROUND)
    assert "número" in index.data(Qt.ItemDataRole.ToolTipRole)
    assert model.setData(index, "650", EDIT)
    assert index.data(Qt.ItemDataRole.BackgroundRole) is None


def test_inline_validation(setup):
    _, model, _ = setup
    model.setData(model.index(1, Column.WIDTH), "3000", EDIT)
    model.setData(model.index(1, Column.HEIGHT), "3000", EDIT)
    for column in (Column.WIDTH, Column.HEIGHT):
        index = model.index(1, column)
        assert index.data(Qt.ItemDataRole.BackgroundRole) == QColor(ERROR_BACKGROUND)
        assert "no cabe" in index.data(Qt.ItemDataRole.ToolTipRole)
    model.setData(model.index(1, Column.THICKNESS), "15", EDIT)
    assert "es de 15 mm" in model.index(1, Column.THICKNESS).data(Qt.ItemDataRole.ToolTipRole)
    model.setData(model.index(1, Column.QUANTITY), 0, EDIT)
    assert model.cell_issues(1, Column.QUANTITY)[0].location == (0, 1)
    assert model.index(0, Column.WIDTH).data(Qt.ItemDataRole.BackgroundRole) is None


def test_add_duplicate_remove_move(setup, qtbot):
    _, model, furniture = setup
    with qtbot.waitSignal(model.pieces_changed):
        row = model.add_piece()
    assert row == 2 and model.rowCount() == 3
    new = furniture.pieces[2]
    assert new.name == "Pieza 3" and new.thickness == PLATE.thickness and new.width == 0
    assert model.cell_issues(2, Column.WIDTH)  # medidas en cero → error visible

    assert model.duplicate_piece(0) == 1
    assert [p.name for p in furniture.pieces] == ["Lateral", "Lateral (copia)", "Tapa", "Pieza 3"]
    assert model.move_piece(3, -1) == 2
    assert model.move_piece(0, 1) == 1
    assert model.move_piece(0, -1) == 0  # ya está arriba
    assert [p.name for p in furniture.pieces] == ["Lateral (copia)", "Lateral", "Pieza 3", "Tapa"]
    model.remove_pieces([0, 2])
    assert [p.name for p in furniture.pieces] == ["Lateral", "Tapa"]
    assert model.rowCount() == 2


def test_no_furniture(qtbot):
    model = PiecesTableModel(UnitsDisplay())
    assert model.rowCount() == 0
    with pytest.raises(RuntimeError):
        model.add_piece()


def test_delegate_combos(setup, qtbot):
    _, model, furniture = setup
    parent = QWidget()
    qtbot.addWidget(parent)
    delegate = PiecesDelegate(model)
    index = model.index(0, Column.CATEGORY)
    editor = delegate.createEditor(parent, QStyleOptionViewItem(), index)
    assert isinstance(editor, QComboBox) and editor.count() == len(PieceCategory)
    delegate.setEditorData(editor, index)
    assert editor.currentData() == "lateral"
    editor.setCurrentIndex(editor.findData("estante"))
    delegate.setModelData(editor, model, index)
    assert furniture.pieces[0].category is PieceCategory.ESTANTE

    material = model.index(0, Column.MATERIAL)
    editor = delegate.createEditor(parent, QStyleOptionViewItem(), material)
    assert [editor.itemData(i) for i in range(editor.count())] == [None, 7]
