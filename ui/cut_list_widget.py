"""Pestañas inferiores **Lista de cortes** y **Secuencia** del resultado.

Ambas tablas son ordenables y se filtran por placa. La selección se sincroniza con el
diagrama: ``piece_selected`` / ``cut_selected`` al elegir una fila, y ``select_piece`` /
``select_cut`` para resaltar la fila de lo que el usuario eligió en el diagrama.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QTableView,
    QTabWidget,
    QWidget,
)

from models.plan_corte import Cut, CutOrientation
from models.resultado import OptimizationResult, Placement
from ui.units_display import UnitsDisplay

_Index = QModelIndex | QPersistentModelIndex

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
"""Valor crudo para ordenar (números como números, no como texto)."""
SHEET_ROLE = Qt.ItemDataRole.UserRole + 2

TAB_CUT_LIST, TAB_SEQUENCE = 0, 1
ALL_SHEETS = -1


class PieceColumn(IntEnum):
    NUMBER = 0
    PIECE = 1
    WIDTH = 2
    HEIGHT = 3
    SHEET = 4
    X = 5
    Y = 6
    ROTATED = 7


class SequenceColumn(IntEnum):
    SHEET = 0
    CUT = 1
    LEVEL = 2
    ORIENTATION = 3
    FENCE = 4
    LENGTH = 5
    RESULTING = 6


PIECE_HEADERS = ["Nº", "Pieza", "Ancho", "Alto", "Placa", "X", "Y", "Rotación"]
SEQUENCE_HEADERS = [
    "Placa",
    "Corte",
    "Nivel",
    "Orientación",
    "Medida de tope",
    "Longitud",
    "Resultado",
]
ORIENTATION_LABELS = {CutOrientation.HORIZONTAL: "Horizontal", CutOrientation.VERTICAL: "Vertical"}
LENGTH_PIECE_COLUMNS = {PieceColumn.WIDTH, PieceColumn.HEIGHT, PieceColumn.X, PieceColumn.Y}


@dataclass(frozen=True)
class PieceRow:
    number: int
    sheet_index: int
    placement_index: int
    placement: Placement


@dataclass(frozen=True)
class CutRow:
    sheet_index: int
    cut: Cut


class _ResultTableModel(QAbstractTableModel):
    headers: list[str] = []

    def __init__(self, units: UnitsDisplay, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.units = units
        self.rows: list[Any] = []
        units.unit_changed.connect(lambda _unit: self._units_changed())

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.headers)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._header(section)
        return None

    def _header(self, section: int) -> str:
        return self.headers[section]

    def _units_changed(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
        if self.rows:
            last = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(self.index(0, 0), last)


class PieceListModel(_ResultTableModel):
    """Una fila por pieza colocada, numeradas en el orden placa → colocación."""

    headers = PIECE_HEADERS

    def set_result(self, result: OptimizationResult | None) -> None:
        self.beginResetModel()
        self.rows = []
        for sheet in result.sheets if result else ():
            for i, placement in enumerate(sheet.placements):
                self.rows.append(PieceRow(len(self.rows) + 1, sheet.index, i, placement))
        self.endResetModel()

    def _header(self, section: int) -> str:
        text = self.headers[section]
        return f"{text} ({self.units.symbol})" if section in LENGTH_PIECE_COLUMNS else text

    def row_of(self, sheet_index: int, placement_index: int) -> int | None:
        for r, row in enumerate(self.rows):
            if row.sheet_index == sheet_index and row.placement_index == placement_index:
                return r
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row: PieceRow = self.rows[index.row()]
        p = row.placement
        col = PieceColumn(index.column())
        if role == SHEET_ROLE:
            return row.sheet_index
        raw: dict[PieceColumn, Any] = {
            PieceColumn.NUMBER: row.number,
            PieceColumn.PIECE: p.piece.label,
            PieceColumn.WIDTH: p.width,
            PieceColumn.HEIGHT: p.height,
            PieceColumn.SHEET: row.sheet_index + 1,
            PieceColumn.X: p.x,
            PieceColumn.Y: p.y,
            PieceColumn.ROTATED: int(p.rotated),
        }
        if role == SORT_ROLE:
            return raw[col]
        if role == Qt.ItemDataRole.DisplayRole:
            if col in LENGTH_PIECE_COLUMNS:
                return self.units.format(raw[col])
            if col is PieceColumn.ROTATED:
                return "Sí ⟲" if p.rotated else "No"
            return str(raw[col])
        if role == Qt.ItemDataRole.TextAlignmentRole and col is not PieceColumn.PIECE:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{p.piece.label} ({p.piece.spec.category.label})"
        return None


class SequenceModel(_ResultTableModel):
    """Secuencia de cortes de escuadradora de cada placa (``CutPlan.cuts``)."""

    headers = SEQUENCE_HEADERS

    def set_result(self, result: OptimizationResult | None) -> None:
        self.beginResetModel()
        self.rows = [
            CutRow(sheet.index, cut)
            for sheet in (result.sheets if result else ())
            if sheet.cut_plan is not None
            for cut in sheet.cut_plan.cuts
        ]
        self.endResetModel()

    def _header(self, section: int) -> str:
        text = self.headers[section]
        if section in (SequenceColumn.FENCE, SequenceColumn.LENGTH):
            return f"{text} ({self.units.symbol})"
        return text

    def row_of(self, sheet_index: int, cut_order: int) -> int | None:
        for r, row in enumerate(self.rows):
            if row.sheet_index == sheet_index and row.cut.order == cut_order:
                return r
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row: CutRow = self.rows[index.row()]
        c = row.cut
        col = SequenceColumn(index.column())
        if role == SHEET_ROLE:
            return row.sheet_index
        if role == SORT_ROLE:
            return {
                SequenceColumn.SHEET: row.sheet_index + 1,
                SequenceColumn.CUT: c.order,
                SequenceColumn.LEVEL: c.level,
                SequenceColumn.ORIENTATION: c.orientation.value,
                SequenceColumn.FENCE: c.fence_distance,
                SequenceColumn.LENGTH: c.length,
                SequenceColumn.RESULTING: ", ".join(c.resulting_labels(self.units.unit)),
            }[col]
        if role == Qt.ItemDataRole.DisplayRole:
            return {
                SequenceColumn.SHEET: str(row.sheet_index + 1),
                SequenceColumn.CUT: f"CORTE {c.order}",
                SequenceColumn.LEVEL: "0 · refilado" if c.is_trim else str(c.level),
                SequenceColumn.ORIENTATION: ORIENTATION_LABELS[c.orientation],
                SequenceColumn.FENCE: self.units.format(c.fence_distance),
                SequenceColumn.LENGTH: self.units.format(c.length),
                SequenceColumn.RESULTING: ", ".join(c.resulting_labels(self.units.unit)),
            }[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (
            SequenceColumn.FENCE,
            SequenceColumn.LENGTH,
            SequenceColumn.SHEET,
        ):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"Región: {c.region}" if c.region else None
        return None


class SheetFilterProxy(QSortFilterProxyModel):
    """Ordena por ``SORT_ROLE`` y deja ver solo una placa (o todas)."""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.sheet_index = ALL_SHEETS
        self.setSortRole(SORT_ROLE)

    def set_sheet(self, sheet_index: int) -> None:
        self.sheet_index = sheet_index
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:  # noqa: N802
        if self.sheet_index == ALL_SHEETS:
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        return index.data(SHEET_ROLE) == self.sheet_index


def _make_table(proxy: SheetFilterProxy) -> QTableView:
    table = QTableView()
    table.setModel(proxy)
    table.setSortingEnabled(True)
    table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table


class CutListWidget(QTabWidget):
    """Pestañas Lista de cortes / Secuencia con filtro de placa en la esquina."""

    piece_selected = Signal(int, int)
    """(índice de placa, índice de la colocación en la placa)."""
    cut_selected = Signal(int, int)
    """(índice de placa, número de corte)."""

    def __init__(self, units: UnitsDisplay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.units = units
        self._syncing = False

        self.piece_model = PieceListModel(units, self)
        self.piece_proxy = SheetFilterProxy(self)
        self.piece_proxy.setSourceModel(self.piece_model)
        self.piece_table = _make_table(self.piece_proxy)

        self.sequence_model = SequenceModel(units, self)
        self.sequence_proxy = SheetFilterProxy(self)
        self.sequence_proxy.setSourceModel(self.sequence_model)
        self.sequence_table = _make_table(self.sequence_proxy)

        self.addTab(self.piece_table, "Lista de cortes")
        self.addTab(self.sequence_table, "Secuencia")

        self.sheet_filter = QComboBox()
        self.sheet_filter.setToolTip("Filtrar por placa")
        self.setCornerWidget(self.sheet_filter, Qt.Corner.TopRightCorner)
        self.sheet_filter.currentIndexChanged.connect(self._on_filter)

        self.piece_table.selectionModel().selectionChanged.connect(self._on_piece_row)
        self.sequence_table.selectionModel().selectionChanged.connect(self._on_cut_row)
        self.set_result(None)

    def set_result(self, result: OptimizationResult | None) -> None:
        self.piece_model.set_result(result)
        self.sequence_model.set_result(result)
        self.sheet_filter.blockSignals(True)
        self.sheet_filter.clear()
        self.sheet_filter.addItem("Todas las placas", ALL_SHEETS)
        for sheet in result.sheets if result else ():
            self.sheet_filter.addItem(f"Placa {sheet.index + 1}", sheet.index)
        self.sheet_filter.setCurrentIndex(0)
        self.sheet_filter.blockSignals(False)
        self._apply_filter(ALL_SHEETS)

    def set_sheet_filter(self, sheet_index: int) -> None:
        i = self.sheet_filter.findData(sheet_index)
        if i >= 0:
            self.sheet_filter.setCurrentIndex(i)

    def _on_filter(self, combo_index: int) -> None:
        sheet = self.sheet_filter.itemData(combo_index)
        self._apply_filter(ALL_SHEETS if sheet is None else int(sheet))

    def _apply_filter(self, sheet_index: int) -> None:
        self.piece_proxy.set_sheet(sheet_index)
        self.sequence_proxy.set_sheet(sheet_index)

    # ------------------------------------------------------------------ selección
    def _selected_source_row(self, table: QTableView, proxy: SheetFilterProxy) -> int | None:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return None
        return proxy.mapToSource(rows[0]).row()

    def _on_piece_row(self) -> None:
        if self._syncing:
            return
        r = self._selected_source_row(self.piece_table, self.piece_proxy)
        if r is not None:
            row: PieceRow = self.piece_model.rows[r]
            self.piece_selected.emit(row.sheet_index, row.placement_index)

    def _on_cut_row(self) -> None:
        if self._syncing:
            return
        r = self._selected_source_row(self.sequence_table, self.sequence_proxy)
        if r is not None:
            row: CutRow = self.sequence_model.rows[r]
            self.cut_selected.emit(row.sheet_index, row.cut.order)

    def _select_row(
        self, table: QTableView, proxy: SheetFilterProxy, source_row: int, sheet_index: int
    ) -> None:
        if proxy.sheet_index not in (ALL_SHEETS, sheet_index):
            self.set_sheet_filter(sheet_index)
        index = proxy.mapFromSource(proxy.sourceModel().index(source_row, 0))
        self._syncing = True
        try:
            self.setCurrentWidget(table)
            table.selectionModel().select(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
            table.setCurrentIndex(index)
        finally:
            self._syncing = False
        table.scrollTo(index)

    def select_piece(self, sheet_index: int, placement_index: int) -> bool:
        """Selecciona la fila de la pieza (sin emitir ``piece_selected``)."""
        r = self.piece_model.row_of(sheet_index, placement_index)
        if r is None:
            return False
        self._select_row(self.piece_table, self.piece_proxy, r, sheet_index)
        return True

    def select_cut(self, sheet_index: int, cut_order: int) -> bool:
        """Selecciona la fila del corte (sin emitir ``cut_selected``)."""
        r = self.sequence_model.row_of(sheet_index, cut_order)
        if r is None:
            return False
        self._select_row(self.sequence_table, self.sequence_proxy, r, sheet_index)
        return True
