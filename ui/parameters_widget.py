"""Parámetros de corte y de optimización del proyecto."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from models.parametros import CutMode, CuttingParameters, OptimizationLevel
from ui import tooltips
from ui.units_display import ERROR_STYLE, LengthEdit, UnitsDisplay, format_area_input, parse_area_m2
from utils.units import LengthError

LENGTH_FIELDS = (
    "kerf",
    "edge_margin",
    "extra_spacing",
    "min_offcut_width",
    "min_offcut_height",
)


class ParametersWidget(QWidget):
    """Edita ``CuttingParameters``. Emite ``changed(CuttingParameters)`` en cada cambio."""

    changed = Signal(object)

    def __init__(self, units: UnitsDisplay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._params = CuttingParameters()
        self._loading = False

        self.edits: dict[str, LengthEdit] = {
            name: LengthEdit(units, allow_zero=True) for name in LENGTH_FIELDS
        }
        for name, edit in self.edits.items():
            edit.value_changed.connect(lambda value, n=name: self._update(**{n: value}))
        self.min_area_edit = QLineEdit()
        self.min_area_edit.setToolTip("Área mínima en m²")
        self.min_area_edit.editingFinished.connect(self._on_area_edited)

        self.rotation_check = QCheckBox("Permitir rotación de piezas")
        self.rotation_check.toggled.connect(lambda v: self._update(allow_rotation=v))
        self.level_combo = QComboBox()
        for level in OptimizationLevel:
            self.level_combo.addItem(level.label, level)
        self.level_combo.currentIndexChanged.connect(
            lambda _i: self._update(level=self.level_combo.currentData())
        )
        self.mode_combo = QComboBox()
        for mode in CutMode:
            self.mode_combo.addItem(mode.label, mode)
        self.mode_combo.currentIndexChanged.connect(
            lambda _i: self._update(cut_mode=self.mode_combo.currentData())
        )
        self.stock_check = QCheckBox("Usar primero placas del inventario")
        self.stock_check.toggled.connect(lambda v: self._update(use_stock_first=v))
        self.offcuts_check = QCheckBox("Usar retazos del stock")
        self.offcuts_check.toggled.connect(lambda v: self._update(use_offcuts_first=v))

        for name, tip in (
            ("kerf", tooltips.KERF),
            ("edge_margin", tooltips.EDGE_MARGIN),
            ("extra_spacing", tooltips.EXTRA_SPACING),
            ("min_offcut_width", tooltips.MIN_OFFCUT),
            ("min_offcut_height", tooltips.MIN_OFFCUT),
        ):
            self.edits[name].set_help(tip)
        self.rotation_check.setToolTip(tooltips.ROTATION)
        self.level_combo.setToolTip(tooltips.LEVEL)
        self.mode_combo.setToolTip(tooltips.CUT_MODE)

        cut_box = QGroupBox("Corte")
        cut_form = QFormLayout(cut_box)
        cut_form.addRow("Kerf (espesor de sierra)", self.edits["kerf"])
        cut_form.addRow("Margen de refilado", self.edits["edge_margin"])
        cut_form.addRow("Separación adicional", self.edits["extra_spacing"])
        cut_form.addRow(self.rotation_check)

        opt_box = QGroupBox("Optimización")
        opt_form = QFormLayout(opt_box)
        opt_form.addRow("Nivel", self.level_combo)
        opt_form.addRow("Máquina", self.mode_combo)
        opt_form.addRow(self.stock_check)
        opt_form.addRow(self.offcuts_check)

        offcut_box = QGroupBox("Retazos reutilizables (mínimos)")
        offcut_form = QFormLayout(offcut_box)
        offcut_form.addRow("Ancho mínimo", self.edits["min_offcut_width"])
        offcut_form.addRow("Alto mínimo", self.edits["min_offcut_height"])
        offcut_form.addRow("Área mínima (m²)", self.min_area_edit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(cut_box)
        layout.addWidget(opt_box)
        layout.addWidget(offcut_box)
        layout.addStretch(1)
        self.set_params(self._params)

    @property
    def params(self) -> CuttingParameters:
        return self._params

    def set_params(self, params: CuttingParameters) -> None:
        self._params = params
        self._loading = True
        try:
            for name, edit in self.edits.items():
                edit.set_value(getattr(params, name))
            self.min_area_edit.setText(format_area_input(params.min_offcut_area))
            self.min_area_edit.setStyleSheet("")
            self.rotation_check.setChecked(params.allow_rotation)
            self.level_combo.setCurrentIndex(self.level_combo.findData(params.level))
            self.mode_combo.setCurrentIndex(self.mode_combo.findData(params.cut_mode))
            self.stock_check.setChecked(params.use_stock_first)
            self.offcuts_check.setChecked(params.use_offcuts_first)
        finally:
            self._loading = False

    def field_widget(self, field: str) -> QWidget | None:
        """Widget que edita un campo (para enfocar un ``ValidationIssue``)."""
        if field == "min_offcut_area":
            return self.min_area_edit
        return self.edits.get(field)

    def _on_area_edited(self) -> None:
        try:
            area = parse_area_m2(self.min_area_edit.text())
        except LengthError as exc:
            self.min_area_edit.setStyleSheet(ERROR_STYLE)
            self.min_area_edit.setToolTip(str(exc))
            return
        self.min_area_edit.setStyleSheet("")
        self.min_area_edit.setToolTip("Área mínima en m²")
        self._update(min_offcut_area=area)

    def _update(self, **changes: object) -> None:
        if self._loading:
            return
        new = replace(self._params, **changes)  # type: ignore[arg-type]
        if new != self._params:
            self._params = new
            self.changed.emit(new)
