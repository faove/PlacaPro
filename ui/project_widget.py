"""Datos del proyecto: nombre, descripción y muebles (con dimensiones generales opcionales)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.proyecto import Furniture, FurnitureDimensions, Project
from ui.units_display import LengthEdit, UnitsDisplay


class ProjectWidget(QWidget):
    """Edita el ``Project`` en el sitio.

    * ``changed``: cualquier modificación.
    * ``furniture_changed(int)``: se agregó, renombró o eliminó un mueble (índice a mostrar).
    * ``furniture_selected(int)``: el usuario eligió un mueble de la lista.
    """

    changed = Signal()
    furniture_changed = Signal(int)
    furniture_selected = Signal(int)

    def __init__(self, units: UnitsDisplay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: Project | None = None
        self._loading = False

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nombre del proyecto")
        self.name_edit.textEdited.connect(self._on_name_edited)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Descripción (opcional)")
        self.description_edit.setMaximumHeight(60)
        self.description_edit.textChanged.connect(self._on_description_changed)

        self.furniture_list = QListWidget()
        self.furniture_list.setMaximumHeight(110)
        self.furniture_list.currentRowChanged.connect(self._on_furniture_row_changed)
        self.furniture_list.itemChanged.connect(self._on_furniture_renamed)
        self.add_furniture_button = QPushButton("Agregar")
        self.rename_furniture_button = QPushButton("Renombrar")
        self.remove_furniture_button = QPushButton("Eliminar")
        self.add_furniture_button.clicked.connect(self.add_furniture)
        self.rename_furniture_button.clicked.connect(self._rename_current)
        self.remove_furniture_button.clicked.connect(self.remove_current_furniture)

        self.dimensions_group = QGroupBox("Dimensiones generales del mueble (opcional)")
        self.dimensions_group.setCheckable(True)
        self.dimensions_group.setChecked(False)
        self.dimensions_group.toggled.connect(self._on_dimensions_edited)
        self.dim_width = LengthEdit(units)
        self.dim_height = LengthEdit(units)
        self.dim_depth = LengthEdit(units)
        dims_form = QFormLayout(self.dimensions_group)
        for label, edit in (
            ("Ancho", self.dim_width),
            ("Alto", self.dim_height),
            ("Profundidad", self.dim_depth),
        ):
            edit.value_changed.connect(self._on_dimensions_edited)
            dims_form.addRow(label, edit)

        form = QFormLayout()
        form.addRow("Nombre", self.name_edit)
        form.addRow("Descripción", self.description_edit)
        buttons = QHBoxLayout()
        for button in (
            self.add_furniture_button,
            self.rename_furniture_button,
            self.remove_furniture_button,
        ):
            buttons.addWidget(button)
        furniture_box = QGroupBox("Muebles")
        furniture_layout = QVBoxLayout(furniture_box)
        furniture_layout.addWidget(self.furniture_list)
        furniture_layout.addLayout(buttons)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(form)
        layout.addWidget(furniture_box)
        layout.addWidget(self.dimensions_group)
        layout.addStretch(1)

    # -- carga
    def set_project(self, project: Project) -> None:
        self.project = project
        self._loading = True
        try:
            self.name_edit.setText(project.name)
            self.description_edit.setPlainText(project.description)
            self._fill_furniture_list(0)
        finally:
            self._loading = False

    def _fill_furniture_list(self, select: int) -> None:
        assert self.project is not None
        was_loading, self._loading = self._loading, True
        try:
            self.furniture_list.clear()
            for item in self.project.furniture:
                entry = QListWidgetItem(item.name)
                entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsEditable)
                self.furniture_list.addItem(entry)
            count = len(self.project.furniture)
            self.furniture_list.setCurrentRow(min(select, count - 1) if count else -1)
        finally:
            self._loading = was_loading
        self.remove_furniture_button.setEnabled(len(self.project.furniture) > 1)
        self._load_dimensions()

    def current_furniture(self) -> Furniture | None:
        row = self.furniture_list.currentRow()
        if self.project is None or not 0 <= row < len(self.project.furniture):
            return None
        return self.project.furniture[row]

    def _load_dimensions(self) -> None:
        furniture = self.current_furniture()
        was_loading, self._loading = self._loading, True
        try:
            dims = furniture.dimensions if furniture else None
            self.dimensions_group.setEnabled(furniture is not None)
            self.dimensions_group.setChecked(dims is not None)
            self.dim_width.set_value(dims.width if dims else 0)
            self.dim_height.set_value(dims.height if dims else 0)
            self.dim_depth.set_value(dims.depth if dims else 0)
        finally:
            self._loading = was_loading

    # -- edición
    def _on_name_edited(self, text: str) -> None:
        if self.project is not None and not self._loading:
            self.project.name = text
            self.changed.emit()

    def _on_description_changed(self) -> None:
        if self.project is not None and not self._loading:
            self.project.description = self.description_edit.toPlainText()
            self.changed.emit()

    def _on_furniture_row_changed(self, row: int) -> None:
        if self._loading:
            return
        self._load_dimensions()
        if row >= 0:
            self.furniture_selected.emit(row)

    def select_furniture(self, row: int) -> None:
        if row != self.furniture_list.currentRow():
            self.furniture_list.setCurrentRow(row)

    def _on_furniture_renamed(self, entry: QListWidgetItem) -> None:
        if self._loading or self.project is None:
            return
        row = self.furniture_list.row(entry)
        name = entry.text().strip()
        if not name:
            # Un mueble sin nombre no tiene sentido: se restaura el anterior.
            self._loading = True
            entry.setText(self.project.furniture[row].name)
            self._loading = False
            return
        if name != self.project.furniture[row].name:
            self.project.furniture[row].name = name
            self.furniture_changed.emit(row)
            self.changed.emit()

    def _rename_current(self) -> None:
        entry = self.furniture_list.currentItem()
        if entry is not None:
            self.furniture_list.editItem(entry)

    def add_furniture(self) -> None:
        if self.project is None:
            return
        self.project.furniture.append(Furniture(name=f"Mueble {len(self.project.furniture) + 1}"))
        row = len(self.project.furniture) - 1
        self._fill_furniture_list(row)
        self.furniture_changed.emit(row)
        self.changed.emit()

    def remove_current_furniture(self, *, confirm: bool = True) -> None:
        furniture = self.current_furniture()
        if self.project is None or furniture is None or len(self.project.furniture) <= 1:
            return
        if confirm and furniture.pieces:
            answer = QMessageBox.question(
                self,
                "Eliminar mueble",
                f"¿Eliminar «{furniture.name}» y sus {len(furniture.pieces)} filas de piezas?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        row = self.furniture_list.currentRow()
        del self.project.furniture[row]
        select = min(row, len(self.project.furniture) - 1)
        self._fill_furniture_list(select)
        self.furniture_changed.emit(select)
        self.changed.emit()

    def _on_dimensions_edited(self, *_args: object) -> None:
        furniture = self.current_furniture()
        if self._loading or furniture is None:
            return
        dims = None
        if self.dimensions_group.isChecked():
            dims = FurnitureDimensions(
                self.dim_width.value(), self.dim_height.value(), self.dim_depth.value()
            )
        if dims != furniture.dimensions:
            furniture.dimensions = dims
            self.changed.emit()
