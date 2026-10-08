"""Lista de piezas: ``QAbstractTableModel`` editable con validación en línea.

El modelo edita en el sitio la lista ``Furniture.pieces`` del mueble seleccionado
(``PieceSpec`` es inmutable: cada edición la reemplaza con ``dataclasses.replace``).
Las celdas con errores se pintan en rojo con el motivo en el tooltip.
"""

from __future__ import annotations

from dataclasses import replace
from enum import IntEnum
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from models.parametros import CuttingParameters
from models.pieza import GrainDirection, PieceCategory, PieceSpec
from models.placa import PlateFormat
from models.proyecto import Furniture, Project
from models.validation import IssueCode, Severity, ValidationIssue, validate_piece
from ui.theme import ERROR_BACKGROUND, WARNING_COLOR
from ui.units_display import UnitsDisplay
from utils.units import LengthError

_Index = QModelIndex | QPersistentModelIndex


class Column(IntEnum):
    NAME = 0
    CATEGORY = 1
    QUANTITY = 2
    WIDTH = 3
    HEIGHT = 4
    THICKNESS = 5
    MATERIAL = 6
    ROTATE = 7
    GRAIN = 8
    FIXED = 9


HEADERS = {
    Column.NAME: "Nombre",
    Column.CATEGORY: "Categoría",
    Column.QUANTITY: "Cant.",
    Column.WIDTH: "Ancho",
    Column.HEIGHT: "Alto",
    Column.THICKNESS: "Espesor",
    Column.MATERIAL: "Material",
    Column.ROTATE: "Rotar",
    Column.GRAIN: "Veta",
    Column.FIXED: "Orient. fija",
}
LENGTH_COLUMNS = {Column.WIDTH: "width", Column.HEIGHT: "height", Column.THICKNESS: "thickness"}
CHECK_COLUMNS = {Column.ROTATE: "can_rotate", Column.FIXED: "fixed_orientation"}

FIELD_COLUMNS: dict[str, tuple[Column, ...]] = {
    "name": (Column.NAME,),
    "quantity": (Column.QUANTITY,),
    "width": (Column.WIDTH,),
    "height": (Column.HEIGHT,),
    "thickness": (Column.THICKNESS,),
    "material_id": (Column.MATERIAL,),
    "grain": (Column.GRAIN,),
}
"""Campo de un ``ValidationIssue`` → columnas que se resaltan."""

NO_MATERIAL = "Según placa"


def issue_columns(issue: ValidationIssue) -> tuple[Column, ...]:
    if issue.code is IssueCode.PIECE_LARGER_THAN_PLATE:
        return (Column.WIDTH, Column.HEIGHT)
    return FIELD_COLUMNS.get(issue.field or "", (Column.NAME,))


class PiecesTableModel(QAbstractTableModel):
    """Piezas de un mueble. Emite ``pieces_changed`` tras cada modificación."""

    pieces_changed = Signal()

    def __init__(self, units: UnitsDisplay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.units = units
        self._furniture: Furniture | None = None
        self._furniture_index = 0
        self.plate: PlateFormat | None = None
        self.params = CuttingParameters()
        self.materials: dict[int, str] = {}
        self._issues: dict[tuple[int, int], list[ValidationIssue]] = {}
        self._input_errors: dict[tuple[int, int], str] = {}
        units.unit_changed.connect(self._on_unit_changed)

    # -- contexto
    @property
    def pieces(self) -> list[PieceSpec]:
        return self._furniture.pieces if self._furniture is not None else []

    def set_furniture(self, furniture: Furniture | None, furniture_index: int = 0) -> None:
        self.beginResetModel()
        self._furniture = furniture
        self._furniture_index = furniture_index
        self._input_errors.clear()
        self._revalidate()
        self.endResetModel()

    def set_context(
        self, plate: PlateFormat | None, params: CuttingParameters, materials: dict[int, str]
    ) -> None:
        """Placa, parámetros y materiales contra los que se valida y se muestran las piezas."""
        self.plate = plate
        self.params = params
        self.materials = materials
        self._revalidate()
        self._emit_all_changed()

    def _on_unit_changed(self, _unit: object) -> None:
        self._input_errors.clear()
        self._emit_all_changed()
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(Column) - 1)

    def _emit_all_changed(self) -> None:
        if self.rowCount():
            last = self.index(self.rowCount() - 1, len(Column) - 1)
            self.dataChanged.emit(self.index(0, 0), last)

    # -- validación
    def _revalidate(self) -> None:
        self._issues = {}
        for row, spec in enumerate(self.pieces):
            location = (self._furniture_index, row)
            for issue in validate_piece(spec, self.plate, self.params, location=location):
                for column in issue_columns(issue):
                    self._issues.setdefault((row, column), []).append(issue)

    def cell_issues(self, row: int, column: int) -> list[ValidationIssue]:
        return self._issues.get((row, column), [])

    def input_error(self, row: int, column: int) -> str | None:
        return self._input_errors.get((row, column))

    # -- API de QAbstractTableModel
    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.pieces)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(Column)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        column = Column(section)
        title = HEADERS[column]
        return f"{title} ({self.units.symbol})" if column in LENGTH_COLUMNS else title

    def flags(self, index: _Index) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if Column(index.column()) in CHECK_COLUMNS:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base | Qt.ItemFlag.ItemIsEditable

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        spec = self.pieces[index.row()]
        column = Column(index.column())
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(spec, column)
        if role == Qt.ItemDataRole.EditRole:
            return self._edit_value(spec, column)
        if role == Qt.ItemDataRole.CheckStateRole and column in CHECK_COLUMNS:
            checked = getattr(spec, CHECK_COLUMNS[column])
            return Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.TextAlignmentRole and column in (
            Column.QUANTITY,
            *LENGTH_COLUMNS,
        ):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole:
            return self._background(index.row(), column)
        if role == Qt.ItemDataRole.ToolTipRole:
            messages = [i.message for i in self.cell_issues(index.row(), column)]
            if error := self.input_error(index.row(), column):
                messages.insert(0, error)
            return "\n".join(messages) or None
        return None

    def _display(self, spec: PieceSpec, column: Column) -> Any:
        if column is Column.NAME:
            return spec.name
        if column is Column.CATEGORY:
            return spec.category.label
        if column is Column.QUANTITY:
            return spec.quantity
        if column in LENGTH_COLUMNS:
            return self.units.format(getattr(spec, LENGTH_COLUMNS[column]))
        if column is Column.MATERIAL:
            if spec.material_id is None:
                return NO_MATERIAL
            return self.materials.get(spec.material_id, f"#{spec.material_id}")
        if column is Column.GRAIN:
            return spec.grain.label
        return None

    def _edit_value(self, spec: PieceSpec, column: Column) -> Any:
        if column is Column.CATEGORY:
            return spec.category.value
        if column is Column.GRAIN:
            return spec.grain.value
        if column is Column.MATERIAL:
            return spec.material_id
        return self._display(spec, column)

    def _background(self, row: int, column: Column) -> QColor | None:
        issues = self.cell_issues(row, column)
        if self.input_error(row, column) or any(i.severity is Severity.ERROR for i in issues):
            return QColor(ERROR_BACKGROUND)
        if issues:
            color = QColor(WARNING_COLOR)
            color.setAlpha(60)
            return color
        return None

    def setData(  # noqa: N802
        self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if not index.isValid():
            return False
        row, column = index.row(), Column(index.column())
        spec = self.pieces[row]
        key = (row, int(column))
        try:
            if role == Qt.ItemDataRole.CheckStateRole and column in CHECK_COLUMNS:
                checked = Qt.CheckState(value) == Qt.CheckState.Checked
                new = replace(spec, **{CHECK_COLUMNS[column]: checked})
            elif role != Qt.ItemDataRole.EditRole:
                return False
            elif column is Column.NAME:
                new = replace(spec, name=str(value).strip())
            elif column is Column.CATEGORY:
                new = replace(spec, category=PieceCategory(value))
            elif column is Column.QUANTITY:
                new = replace(spec, quantity=int(value))
            elif column in LENGTH_COLUMNS:
                length = self.units.parse(str(value), allow_zero=True)
                new = replace(spec, **{LENGTH_COLUMNS[column]: length})
            elif column is Column.MATERIAL:
                new = replace(spec, material_id=None if value is None else int(value))
            elif column is Column.GRAIN:
                new = replace(spec, grain=GrainDirection(value))
            else:
                return False
        except (LengthError, ValueError) as exc:
            self._input_errors[key] = str(exc)
            self.dataChanged.emit(index, index)
            return False
        self._input_errors.pop(key, None)
        if new == spec:
            self.dataChanged.emit(index, index)
            return True
        self.pieces[row] = new
        self._revalidate()
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(Column) - 1))
        self.pieces_changed.emit()
        return True

    # -- operaciones de filas
    def _new_piece(self) -> PieceSpec:
        thickness = self.plate.thickness if self.plate is not None else 0
        return PieceSpec(f"Pieza {len(self.pieces) + 1}", 1, 0, 0, thickness)

    def _structure_changed(self) -> None:
        self._input_errors.clear()
        self._revalidate()
        self._emit_all_changed()
        self.pieces_changed.emit()

    def add_piece(self, spec: PieceSpec | None = None, row: int | None = None) -> int:
        """Inserta una pieza (al final por defecto). Devuelve la fila. Requiere un mueble."""
        if self._furniture is None:
            raise RuntimeError("No hay un mueble seleccionado")
        row = len(self.pieces) if row is None else row
        self.beginInsertRows(QModelIndex(), row, row)
        self.pieces.insert(row, spec if spec is not None else self._new_piece())
        self.endInsertRows()
        self._structure_changed()
        return row

    def duplicate_piece(self, row: int) -> int:
        spec = self.pieces[row]
        return self.add_piece(replace(spec, id=None, name=f"{spec.name} (copia)"), row + 1)

    def remove_pieces(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.pieces[row]
            self.endRemoveRows()
        if rows:
            self._structure_changed()

    def move_piece(self, row: int, delta: int) -> int:
        """Mueve la pieza ``delta`` posiciones (±1). Devuelve la nueva fila."""
        target = row + delta
        if not 0 <= target < len(self.pieces) or delta == 0:
            return row
        # beginMoveRows espera la fila de destino "antes de la cual" insertar.
        dest = target + 1 if delta > 0 else target
        self.beginMoveRows(QModelIndex(), row, row, QModelIndex(), dest)
        self.pieces.insert(target, self.pieces.pop(row))
        self.endMoveRows()
        self._structure_changed()
        return target


class PiecesDelegate(QStyledItemDelegate):
    """Editores: combos de categoría, veta y material; spinbox de cantidad.

    Las longitudes se editan como texto (interpretado con ``Decimal`` en la unidad visible,
    nunca con ``float``).
    """

    def __init__(self, model: PiecesTableModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model

    def _choices(self, column: Column) -> list[tuple[str, Any]] | None:
        if column is Column.CATEGORY:
            return [(c.label, c.value) for c in PieceCategory]
        if column is Column.GRAIN:
            return [(g.label, g.value) for g in GrainDirection]
        if column is Column.MATERIAL:
            return [(NO_MATERIAL, None), *((n, i) for i, n in self.model.materials.items())]
        return None

    def createEditor(  # noqa: N802
        self, parent: QWidget, option: QStyleOptionViewItem, index: _Index
    ) -> QWidget:
        column = Column(index.column())
        choices = self._choices(column)
        if choices is not None:
            combo = QComboBox(parent)
            for label, data in choices:
                combo.addItem(label, data)
            return combo
        if column is Column.QUANTITY:
            spin = QSpinBox(parent)
            spin.setRange(0, 9999)
            return spin
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor: QWidget, index: _Index) -> None:  # noqa: N802
        if isinstance(editor, QComboBox):
            position = editor.findData(index.data(Qt.ItemDataRole.EditRole))
            editor.setCurrentIndex(max(position, 0))
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor: QWidget, model: Any, index: _Index) -> None:  # noqa: N802
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)
            return
        super().setModelData(editor, model, index)


class PiecesWidget(QWidget):
    """Tabla de piezas del mueble elegido con botones Agregar/Duplicar/Eliminar/Subir/Bajar."""

    changed = Signal()

    def __init__(self, units: UnitsDisplay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: Project | None = None
        self.model = PiecesTableModel(units, self)
        self.model.pieces_changed.connect(self._on_pieces_changed)

        self.furniture_combo = QComboBox()
        self.furniture_combo.currentIndexChanged.connect(self._on_furniture_selected)
        self.summary = QLabel()

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(PiecesDelegate(self.model, self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(Column.NAME, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(24)

        self.add_button = QPushButton("Agregar")
        self.duplicate_button = QPushButton("Duplicar")
        self.remove_button = QPushButton("Eliminar")
        self.up_button = QPushButton("▲")
        self.up_button.setToolTip("Subir")
        self.down_button = QPushButton("▼")
        self.down_button.setToolTip("Bajar")
        self.add_button.clicked.connect(self.add_piece)
        self.duplicate_button.clicked.connect(self.duplicate_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button.clicked.connect(lambda: self.move_selected(1))

        top = QHBoxLayout()
        top.addWidget(QLabel("Mueble:"))
        top.addWidget(self.furniture_combo, 1)
        buttons = QHBoxLayout()
        for button in (
            self.add_button,
            self.duplicate_button,
            self.remove_button,
            self.up_button,
            self.down_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.summary)
        self._update_summary()

    # -- carga
    def set_project(self, project: Project) -> None:
        self.project = project
        self.refresh_furniture()

    def refresh_furniture(self, select: int | None = None) -> None:
        """Rehace la lista de muebles (tras agregar/renombrar/eliminar uno)."""
        if self.project is None:
            return
        current = self.furniture_combo.currentIndex() if select is None else select
        self.furniture_combo.blockSignals(True)
        self.furniture_combo.clear()
        for item in self.project.furniture:
            self.furniture_combo.addItem(item.name or "(sin nombre)")
        self.furniture_combo.blockSignals(False)
        count = len(self.project.furniture)
        index = min(max(current, 0), count - 1) if count else -1
        self.furniture_combo.setCurrentIndex(index)
        self._on_furniture_selected(index)

    def select_furniture(self, index: int) -> None:
        if index != self.furniture_combo.currentIndex():
            self.furniture_combo.setCurrentIndex(index)

    def _on_furniture_selected(self, index: int) -> None:
        furniture = None
        if self.project is not None and 0 <= index < len(self.project.furniture):
            furniture = self.project.furniture[index]
        self.model.set_furniture(furniture, max(index, 0))
        enabled = furniture is not None
        for widget in (self.table, self.add_button, self.duplicate_button, self.remove_button):
            widget.setEnabled(enabled)
        self._update_summary()

    def set_context(
        self, plate: PlateFormat | None, params: CuttingParameters, materials: dict[int, str]
    ) -> None:
        self.model.set_context(plate, params, materials)

    # -- acciones
    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def _select_row(self, row: int) -> None:
        self.table.selectRow(row)
        self.table.scrollTo(self.model.index(row, 0))

    def add_piece(self) -> None:
        rows = self._selected_rows()
        row = self.model.add_piece(row=rows[-1] + 1 if rows else None)
        self._select_row(row)
        self.table.edit(self.model.index(row, Column.NAME))

    def duplicate_selected(self) -> None:
        rows = self._selected_rows()
        if rows:
            self._select_row(self.model.duplicate_piece(rows[-1]))

    def remove_selected(self) -> None:
        rows = self._selected_rows()
        self.model.remove_pieces(rows)
        if self.model.rowCount():
            self._select_row(min(rows[0], self.model.rowCount() - 1))

    def move_selected(self, delta: int) -> None:
        rows = self._selected_rows()
        if len(rows) == 1:
            self._select_row(self.model.move_piece(rows[0], delta))

    def focus_cell(self, furniture_index: int, row: int, field: str | None) -> None:
        """Selecciona la celda señalada por un ``ValidationIssue``."""
        self.select_furniture(furniture_index)
        if not 0 <= row < self.model.rowCount():
            return
        column = FIELD_COLUMNS.get(field or "", (Column.NAME,))[0]
        index = self.model.index(row, column)
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index)
        self.table.setFocus()

    def _on_pieces_changed(self) -> None:
        self._update_summary()
        self.changed.emit()

    def _update_summary(self) -> None:
        pieces = self.model.pieces
        total = sum(max(p.quantity, 0) for p in pieces)
        self.summary.setText(f"{len(pieces)} filas · {total} piezas")
