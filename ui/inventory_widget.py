"""Diálogo de inventario: placas enteras disponibles por formato (Datos ▸ Inventario)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.inventory_service import InventoryService
from services.plate_service import PlateService
from ui.units_display import UnitsDisplay

MAX_STOCK = 99999
HEADERS = ["Formato", "Medidas", "Espesor", "Material", "Disponibles"]
COLUMN_STOCK = 4


class InventoryDialog(QDialog):
    """Tabla de formatos con la cantidad disponible editable. «Guardar» escribe solo los
    cambios (la cantidad nunca puede ser negativa)."""

    def __init__(
        self,
        plates: PlateService,
        inventory: InventoryService,
        units: UnitsDisplay,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Inventario de placas")
        self.inventory = inventory
        self.resize(640, 380)

        materials = {m.id: m.name for m in plates.list_materials() if m.id is not None}
        self.formats = plates.list_formats()
        self.original: dict[int, int] = {}
        self.spins: dict[int, QSpinBox] = {}

        self.table = QTableWidget(len(self.formats), len(HEADERS))
        self.table.setHorizontalHeaderLabels(
            [f"{h} ({units.symbol})" if h in ("Medidas", "Espesor") else h for h in HEADERS]
        )
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row, plate in enumerate(self.formats):
            assert plate.id is not None
            quantity = inventory.available_plates(plate.id)
            self.original[plate.id] = quantity
            cells = [
                plate.name,
                f"{units.format(plate.width)} × {units.format(plate.height)}",
                units.format(plate.thickness),
                materials.get(plate.material_id, "") if plate.material_id else "",
            ]
            for col, text in enumerate(cells):
                self.table.setItem(row, col, QTableWidgetItem(text))
            spin = QSpinBox()
            spin.setRange(0, MAX_STOCK)
            spin.setSuffix(" placas")
            spin.setValue(quantity)
            self.spins[plate.id] = spin
            self.table.setCellWidget(row, COLUMN_STOCK, spin)

        hint = QLabel(
            "Las placas del inventario se usan primero si se activa «Usar primero placas del "
            "inventario» en PARÁMETROS. Se descuentan al confirmar un plan de corte."
        )
        hint.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def changes(self) -> dict[int, int]:
        """Formatos cuya cantidad cambió → nueva cantidad."""
        return {
            plate_id: spin.value()
            for plate_id, spin in self.spins.items()
            if spin.value() != self.original[plate_id]
        }

    def set_quantity(self, plate_id: int, quantity: int) -> None:
        self.spins[plate_id].setValue(quantity)

    def save(self) -> dict[int, int]:
        changes = self.changes()
        with self.inventory.db.transaction():
            for plate_id, quantity in changes.items():
                self.inventory.set_available_plates(plate_id, quantity)
        self.original.update(changes)
        return changes

    def accept(self) -> None:
        self.save()
        super().accept()
