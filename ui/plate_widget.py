"""Placa del proyecto: lista de placas guardadas, formulario y stock disponible.

La placa seleccionada en la lista es la del proyecto. El formulario edita un borrador
que solo se persiste con **Guardar placa** (junto con la cantidad en stock).
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.placa import PlateFormat, PlateGrain
from models.validation import ValidationFailed
from services.inventory_service import InventoryService
from services.plate_service import PlateService
from ui import tooltips
from ui.theme import ERROR_COLOR
from ui.units_display import LengthEdit, UnitsDisplay


class PlateWidget(QWidget):
    """* ``plate_selected(object)``: id de la placa elegida para el proyecto (o ``None``).
    * ``plates_changed``: se guardó, duplicó o eliminó una placa.
    """

    plate_selected = Signal(object)
    plates_changed = Signal()

    def __init__(
        self,
        plates: PlateService,
        inventory: InventoryService,
        units: UnitsDisplay,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.plates = plates
        self.inventory = inventory
        self.units = units
        self._editing_id: int | None = None
        self._loading = False

        self.plate_list = QListWidget()
        self.plate_list.setMinimumHeight(110)
        self.plate_list.currentItemChanged.connect(self._on_current_changed)

        self.name_edit = QLineEdit()
        self.width_edit = LengthEdit(units)
        self.height_edit = LengthEdit(units)
        self.thickness_edit = LengthEdit(units)
        self.material_combo = QComboBox()
        self.color_edit = QLineEdit()
        self.supplier_combo = QComboBox()
        self.grain_combo = QComboBox()
        self.grain_combo.setToolTip(tooltips.PLATE_GRAIN)
        for grain in PlateGrain:
            self.grain_combo.addItem(grain.label, grain.value)
        self.stock_spin = QSpinBox()
        self.stock_spin.setRange(0, 99999)
        self.stock_spin.setSuffix(" placas")
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {ERROR_COLOR};")
        self.error_label.hide()

        self.save_button = QPushButton("Guardar placa")
        self.save_button.setDefault(True)
        self.new_button = QPushButton("Nueva")
        self.duplicate_button = QPushButton("Duplicar")
        self.delete_button = QPushButton("Eliminar")
        self.save_button.clicked.connect(self.save_plate)
        self.new_button.clicked.connect(self.new_plate)
        self.duplicate_button.clicked.connect(self.duplicate_plate)
        self.delete_button.clicked.connect(lambda: self.delete_plate())

        list_buttons = QHBoxLayout()
        for button in (self.new_button, self.duplicate_button, self.delete_button):
            list_buttons.addWidget(button)
        form = QFormLayout()
        form.addRow("Nombre", self.name_edit)
        form.addRow("Ancho", self.width_edit)
        form.addRow("Alto", self.height_edit)
        form.addRow("Espesor", self.thickness_edit)
        form.addRow("Material", self.material_combo)
        form.addRow("Color", self.color_edit)
        form.addRow("Proveedor", self.supplier_combo)
        form.addRow("Veta", self.grain_combo)
        form.addRow("Stock disponible", self.stock_spin)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Placas guardadas (la seleccionada se usa en el proyecto):"))
        layout.addWidget(self.plate_list)
        layout.addLayout(list_buttons)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.save_button)
        layout.addStretch(1)

        # El formulario se actualiza solo (LengthEdit); se conserva el borrador.
        units.unit_changed.connect(lambda _unit: self.reload(load_form=False))
        self.reload()

    # -- datos
    def materials(self) -> dict[int, str]:
        return {m.id: m.name for m in self.plates.list_materials() if m.id is not None}

    def reload(self, select_id: int | None = None, *, load_form: bool = True) -> None:
        """Recarga combos y lista. Mantiene la selección actual salvo que se indique otra."""
        if select_id is None:
            select_id = self.selected_plate_id()
        self._loading = True
        try:
            self._fill_combo(self.material_combo, self.materials())
            suppliers = {s.id: s.name for s in self.plates.list_suppliers() if s.id is not None}
            self._fill_combo(self.supplier_combo, suppliers)
            self.plate_list.clear()
            for plate in self.plates.list_formats():
                stock = self.inventory.available_plates(plate.id) if plate.id else 0
                text = f"{plate.name}\n{self._dims(plate)} · stock: {stock}"
                entry = QListWidgetItem(text)
                entry.setData(Qt.ItemDataRole.UserRole, plate.id)
                self.plate_list.addItem(entry)
            self._select_in_list(select_id)
        finally:
            self._loading = False
        if load_form:
            self._load_form(self.selected_plate())

    @staticmethod
    def _fill_combo(combo: QComboBox, items: dict[int, str]) -> None:
        current = combo.currentData()
        combo.clear()
        combo.addItem("—", None)
        for item_id, name in items.items():
            combo.addItem(name, item_id)
        combo.setCurrentIndex(max(combo.findData(current), 0))

    def _dims(self, plate: PlateFormat) -> str:
        w, h, t = (self.units.format(v) for v in (plate.width, plate.height, plate.thickness))
        return f"{w} × {h} × {t} {self.units.symbol}"

    def _select_in_list(self, plate_id: int | None) -> None:
        for row in range(self.plate_list.count()):
            if self.plate_list.item(row).data(Qt.ItemDataRole.UserRole) == plate_id:
                self.plate_list.setCurrentRow(row)
                return
        self.plate_list.setCurrentRow(-1)

    def selected_plate_id(self) -> int | None:
        entry = self.plate_list.currentItem()
        return entry.data(Qt.ItemDataRole.UserRole) if entry is not None else None

    def selected_plate(self) -> PlateFormat | None:
        plate_id = self.selected_plate_id()
        return self.plates.get_format(plate_id) if plate_id is not None else None

    def set_selected_plate(self, plate_id: int | None) -> None:
        """Selecciona la placa del proyecto sin emitir ``plate_selected``."""
        self._loading = True
        try:
            self._select_in_list(plate_id)
        finally:
            self._loading = False
        self._load_form(self.selected_plate())

    # -- formulario
    def _load_form(self, plate: PlateFormat | None) -> None:
        self._editing_id = plate.id if plate else None
        self._show_error(None)
        self.name_edit.setText(plate.name if plate else "")
        self.width_edit.set_value(plate.width if plate else 0)
        self.height_edit.set_value(plate.height if plate else 0)
        self.thickness_edit.set_value(plate.thickness if plate else 0)
        self.color_edit.setText(plate.color if plate else "")
        for combo, value in (
            (self.material_combo, plate.material_id if plate else None),
            (self.supplier_combo, plate.supplier_id if plate else None),
            (self.grain_combo, (plate.grain if plate else PlateGrain.NONE).value),
        ):
            combo.setCurrentIndex(max(combo.findData(value), 0))
        stock = self.inventory.available_plates(plate.id) if plate and plate.id else 0
        self.stock_spin.setValue(stock)
        self.duplicate_button.setEnabled(plate is not None)
        self.delete_button.setEnabled(plate is not None)

    def form_plate(self) -> PlateFormat:
        """Placa armada con los datos del formulario (sin guardar)."""
        return PlateFormat(
            name=self.name_edit.text().strip(),
            width=self.width_edit.value(),
            height=self.height_edit.value(),
            thickness=self.thickness_edit.value(),
            material_id=self.material_combo.currentData(),
            color=self.color_edit.text().strip(),
            supplier_id=self.supplier_combo.currentData(),
            grain=PlateGrain(self.grain_combo.currentData()),
            price_cents=self._current_price(),
            id=self._editing_id,
        )

    def _current_price(self) -> int | None:
        if self._editing_id is None:
            return None
        return self.plates.get_format(self._editing_id).price_cents

    def _show_error(self, message: str | None) -> None:
        self.error_label.setText(message or "")
        self.error_label.setVisible(bool(message))

    def _on_current_changed(self, current: QListWidgetItem | None, _previous: object) -> None:
        if self._loading:
            return
        self._load_form(self.selected_plate())
        self.plate_selected.emit(self.selected_plate_id())

    # -- acciones
    def save_plate(self) -> PlateFormat | None:
        """Guarda el formulario (crea o actualiza) y la cantidad en stock."""
        invalid = [e.error for e in (self.width_edit, self.height_edit, self.thickness_edit)]
        if any(invalid):
            self._show_error(next(e for e in invalid if e))
            return None
        try:
            saved = self.plates.save_format(self.form_plate())
        except ValidationFailed as exc:
            self._show_error("\n".join(i.message for i in exc.report.errors))
            return None
        assert saved.id is not None
        self.inventory.set_available_plates(saved.id, self.stock_spin.value())
        created = self._editing_id is None
        self.reload(saved.id)
        self.plates_changed.emit()
        if created:
            self.plate_selected.emit(saved.id)
        return saved

    def new_plate(self) -> None:
        """Vacía el formulario para crear una placa nueva (se crea al guardarla)."""
        self._loading = True
        self.plate_list.setCurrentRow(-1)
        self._loading = False
        self._load_form(None)
        self.name_edit.setFocus()

    def duplicate_plate(self) -> PlateFormat | None:
        plate = self.selected_plate()
        if plate is None:
            return None
        copy = self.plates.save_format(replace(plate, id=None, name=f"{plate.name} (copia)"))
        self.reload(copy.id)
        self.plates_changed.emit()
        self.plate_selected.emit(copy.id)
        return copy

    def delete_plate(self, *, confirm: bool = True) -> None:
        plate = self.selected_plate()
        if plate is None or plate.id is None:
            return
        if confirm:
            answer = QMessageBox.question(
                self,
                "Eliminar placa",
                f"¿Eliminar la placa «{plate.name}»? Los proyectos que la usan quedarán sin "
                "placa seleccionada.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.plates.delete_format(plate.id)
        self.reload(-1)
        self.plates_changed.emit()
        self.plate_selected.emit(None)
