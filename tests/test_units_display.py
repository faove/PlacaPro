import pytest
from PySide6.QtCore import Qt

from ui.units_display import LengthEdit, UnitsDisplay, format_area_input, parse_area_m2
from utils.units import LengthError, Unit, mm_to_internal

pytestmark = pytest.mark.ui


def test_183_cm_is_1830_mm():
    units = UnitsDisplay(Unit.CM)
    assert units.parse("183") == mm_to_internal(1830)
    assert units.format(mm_to_internal(1830)) == "183"


@pytest.mark.parametrize(
    ("unit", "text", "mm"),
    [
        (Unit.MM, "3,2", "3.2"),
        (Unit.CM, "18,35", "183.5"),
        (Unit.M, "2,82", "2820"),
        (Unit.M, "0,0001", "0.1"),
    ],
)
def test_parse_is_exact(unit, text, mm):
    assert UnitsDisplay(unit).parse(text) == mm_to_internal(mm)


@pytest.mark.parametrize(
    ("unit", "text"), [(Unit.CM, "18,355"), (Unit.MM, "-5"), (Unit.MM, "abc"), (Unit.MM, "0")]
)
def test_parse_rejects_invalid(unit, text):
    with pytest.raises(LengthError):
        UnitsDisplay(unit).parse(text)


def test_unit_changed_signal(qtbot):
    units = UnitsDisplay()
    with qtbot.waitSignal(units.unit_changed) as blocker:
        units.set_unit(Unit.M)
    assert blocker.args == [Unit.M]
    with qtbot.assertNotEmitted(units.unit_changed):
        units.set_unit(Unit.M)


def test_length_edit_typing_in_cm_stores_mm(qtbot):
    units = UnitsDisplay(Unit.CM)
    edit = LengthEdit(units, mm_to_internal(100))
    qtbot.addWidget(edit)
    assert edit.text() == "10"
    edit.clear()
    with qtbot.waitSignal(edit.value_changed) as blocker:
        qtbot.keyClicks(edit, "183")
        qtbot.keyClick(edit, Qt.Key.Key_Return)
    assert blocker.args == [mm_to_internal(1830)]
    assert edit.value() == mm_to_internal(1830)

    units.set_unit(Unit.MM)
    assert edit.text() == "1830"
    units.set_unit(Unit.M)
    assert edit.text() == "1,83"


def test_length_edit_invalid_input_keeps_value(qtbot):
    units = UnitsDisplay()
    edit = LengthEdit(units, mm_to_internal(400))
    qtbot.addWidget(edit)
    edit.setText("40,05")
    with qtbot.assertNotEmitted(edit.value_changed):
        edit.editingFinished.emit()
    assert edit.value() == mm_to_internal(400)
    assert edit.error and "precisión" in edit.error
    assert "border" in edit.styleSheet()

    edit.setText("450")
    edit.editingFinished.emit()
    assert edit.error is None and edit.styleSheet() == ""
    assert edit.value() == mm_to_internal(450)


def test_length_edit_allow_zero(qtbot):
    edit = LengthEdit(UnitsDisplay(), mm_to_internal(3), allow_zero=True)
    qtbot.addWidget(edit)
    edit.setText("0")
    edit.editingFinished.emit()
    assert edit.value() == 0 and edit.error is None


def test_area_m2_roundtrip():
    assert parse_area_m2("0,05") == 5_000_000
    assert format_area_input(5_000_000) == "0,05"
    assert format_area_input(0) == "0"
    for bad in ("-1", "x", "0,000000001"):
        with pytest.raises(LengthError):
            parse_area_m2(bad)
