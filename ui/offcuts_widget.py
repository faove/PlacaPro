"""Pestaña **Retazos**: retazos del resultado actual (con «Guardar en stock») y retazos
disponibles en el stock (filtro por material/espesor, marcar consumido, eliminar)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.resultado import OptimizationResult
from models.retazo import Offcut, OffcutStatus
from services.inventory_service import InventoryService
from ui.units_display import UnitsDisplay
from utils.units import format_area_m2

ALL = -1
STORABLE = (OffcutStatus.REUSABLE, OffcutStatus.IN_STOCK)


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setAlternatingRowColors(True)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setStretchLastSection(True)
    return table


class OffcutsWidget(QWidget):
    """Emite ``result_updated(OptimizationResult)`` al pasar retazos a stock (el resultado
    guardado los marca ``IN_STOCK``) y ``stock_changed()`` al modificar el stock."""

    result_updated = Signal(object)
    stock_changed = Signal()

    def __init__(
        self,
        inventory: InventoryService,
        units: UnitsDisplay,
        materials: dict[int, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inventory = inventory
        self.units = units
        self.materials = materials or {}
        self.result: OptimizationResult | None = None
        self.result_offcuts: list[tuple[int, Offcut]] = []
        self.stock_offcuts: list[Offcut] = []

        # -- retazos del resultado
        self.result_table = _table(["Retazo", "Placa", "Medidas", "Área", "Estado"])
        self.save_selected_button = QPushButton("Guardar seleccionados en stock")
        self.save_all_button = QPushButton("Guardar todos")
        self.result_hint = QLabel()
        self.result_hint.setWordWrap(True)
        result_buttons = QHBoxLayout()
        result_buttons.addWidget(self.save_selected_button)
        result_buttons.addWidget(self.save_all_button)
        result_buttons.addStretch(1)
        result_box = QGroupBox("Retazos de este resultado")
        result_layout = QVBoxLayout(result_box)
        result_layout.addWidget(self.result_table, 1)
        result_layout.addWidget(self.result_hint)
        result_layout.addLayout(result_buttons)

        # -- stock de retazos
        self.material_filter = QComboBox()
        self.thickness_filter = QComboBox()
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Material"))
        filters.addWidget(self.material_filter, 1)
        filters.addWidget(QLabel("Espesor"))
        filters.addWidget(self.thickness_filter, 1)
        self.stock_table = _table(["Nº", "Medidas", "Espesor", "Material", "Área", "Origen"])
        self.consume_button = QPushButton("Marcar consumido")
        self.delete_button = QPushButton("Eliminar")
        stock_buttons = QHBoxLayout()
        stock_buttons.addWidget(self.consume_button)
        stock_buttons.addWidget(self.delete_button)
        stock_buttons.addStretch(1)
        stock_box = QGroupBox("Retazos disponibles en stock")
        stock_layout = QVBoxLayout(stock_box)
        stock_layout.addLayout(filters)
        stock_layout.addWidget(self.stock_table, 1)
        stock_layout.addLayout(stock_buttons)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(result_box)
        splitter.addWidget(stock_box)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.save_selected_button.clicked.connect(lambda: self.save_to_stock(selected_only=True))
        self.save_all_button.clicked.connect(lambda: self.save_to_stock(selected_only=False))
        self.consume_button.clicked.connect(lambda: self.mark_selected_consumed())
        self.delete_button.clicked.connect(lambda: self.delete_selected())
        self.material_filter.currentIndexChanged.connect(lambda _i: self.refresh_stock())
        self.thickness_filter.currentIndexChanged.connect(lambda _i: self.refresh_stock())
        self.result_table.itemSelectionChanged.connect(self._update_buttons)
        self.stock_table.itemSelectionChanged.connect(self._update_buttons)
        units.unit_changed.connect(lambda _unit: self._refresh_all())
        self.set_result(None)

    # ------------------------------------------------------------------ resultado
    def _dims(self, offcut: Offcut) -> str:
        u = self.units
        return f"{u.format(offcut.width)} × {u.format(offcut.height)} {u.symbol}"

    def set_result(self, result: OptimizationResult | None) -> None:
        self.result = result
        self.result_offcuts = [
            (s.index, o)
            for s in (result.sheets if result else ())
            for o in s.offcuts
            if o.status in STORABLE
        ]
        table = self.result_table
        table.setRowCount(len(self.result_offcuts))
        for row, (sheet_index, o) in enumerate(self.result_offcuts):
            cells = [o.label, str(sheet_index + 1), self._dims(o), format_area_m2(o.area)]
            cells.append(o.status.label)
            for col, text in enumerate(cells):
                table.setItem(row, col, QTableWidgetItem(text))
        if result is None:
            self.result_hint.setText("Sin resultado.")
        elif result.id is None:
            self.result_hint.setText("Guarde el proyecto para poder pasar retazos al stock.")
        elif not self.result_offcuts:
            self.result_hint.setText("Este resultado no deja retazos reutilizables.")
        else:
            self.result_hint.setText("")
        self._update_buttons()

    def _selected_rows(self, table: QTableWidget) -> list[int]:
        return sorted({i.row() for i in table.selectedIndexes()})

    def save_to_stock(self, *, selected_only: bool) -> list[Offcut]:
        """Pasa a stock los retazos reutilizables (seleccionados o todos) del resultado."""
        if self.result is None or self.result.id is None:
            return []
        rows = (
            self._selected_rows(self.result_table)
            if selected_only
            else range(len(self.result_offcuts))
        )
        labels = [
            self.result_offcuts[r][1].label
            for r in rows
            if self.result_offcuts[r][1].status is OffcutStatus.REUSABLE
        ]
        if not labels:
            return []
        stored = self.inventory.save_offcuts(self.result.id, labels)
        updated = self.inventory.results.get(self.result.id)
        self.set_result(updated)
        self.refresh_stock()
        self.result_updated.emit(updated)
        self.stock_changed.emit()
        return stored

    # ------------------------------------------------------------------ stock
    def set_materials(self, materials: dict[int, str]) -> None:
        self.materials = materials
        self.refresh_stock()

    def _refill_filters(self, offcuts: list[Offcut]) -> None:
        def refill(combo: QComboBox, items: list[tuple[str, int]]) -> None:
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Todos", ALL)
            for text, value in items:
                combo.addItem(text, value)
            i = combo.findData(current)
            combo.setCurrentIndex(i if i >= 0 else 0)
            combo.blockSignals(False)

        material_ids = sorted({o.material_id for o in offcuts if o.material_id is not None})
        refill(self.material_filter, [(self.materials.get(m, f"#{m}"), m) for m in material_ids])
        thicknesses = sorted({o.thickness for o in offcuts})
        refill(
            self.thickness_filter,
            [(self.units.format(t, with_unit=True), t) for t in thicknesses],
        )

    def refresh_stock(self) -> None:
        everything = self.inventory.available_offcuts()
        self._refill_filters(everything)
        material = self.material_filter.currentData()
        thickness = self.thickness_filter.currentData()
        self.stock_offcuts = self.inventory.available_offcuts(
            material_id=None if material in (None, ALL) else material,
            thickness=None if thickness in (None, ALL) else thickness,
        )
        table = self.stock_table
        table.setRowCount(len(self.stock_offcuts))
        for row, o in enumerate(self.stock_offcuts):
            cells = [
                str(o.id),
                self._dims(o),
                self.units.format(o.thickness, with_unit=True),
                self.materials.get(o.material_id, "") if o.material_id else "",
                format_area_m2(o.area),
                o.notes,
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, o.id)
                table.setItem(row, col, item)
        self._update_buttons()

    def selected_stock_ids(self) -> list[int]:
        return [self.stock_offcuts[r].id for r in self._selected_rows(self.stock_table)]  # type: ignore[misc]

    def mark_selected_consumed(self) -> int:
        ids = self.selected_stock_ids()
        with self.inventory.db.transaction():
            for offcut_id in ids:
                self.inventory.mark_offcut_consumed(offcut_id)
        if ids:
            self.refresh_stock()
            self.stock_changed.emit()
        return len(ids)

    def delete_selected(self, *, confirm: bool = True) -> int:
        ids = self.selected_stock_ids()
        if not ids:
            return 0
        if confirm:
            answer = QMessageBox.question(
                self,
                "Eliminar retazos",
                f"¿Eliminar {len(ids)} retazo{'s' if len(ids) != 1 else ''} del stock?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return 0
        with self.inventory.db.transaction():
            for offcut_id in ids:
                self.inventory.delete_offcut(offcut_id)
        self.refresh_stock()
        self.stock_changed.emit()
        return len(ids)

    # ------------------------------------------------------------------ estado
    def _refresh_all(self) -> None:
        self.set_result(self.result)
        self.refresh_stock()

    def _update_buttons(self) -> None:
        saved = self.result is not None and self.result.id is not None
        pending = [o for _, o in self.result_offcuts if o.status is OffcutStatus.REUSABLE]
        selected_pending = any(
            self.result_offcuts[r][1].status is OffcutStatus.REUSABLE
            for r in self._selected_rows(self.result_table)
        )
        self.save_all_button.setEnabled(saved and bool(pending))
        self.save_selected_button.setEnabled(saved and selected_pending)
        has_stock_selection = bool(self._selected_rows(self.stock_table))
        self.consume_button.setEnabled(has_stock_selection)
        self.delete_button.setEnabled(has_stock_selection)
