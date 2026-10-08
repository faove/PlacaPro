"""Unidad de presentación (mm/cm/m) y campos de longitud.

La unidad elegida en el menú Ver afecta solo a cómo se muestran e interpretan los
valores: el modelo sigue en unidades internas (dmm, ``int``) y la conversión es exacta
con ``Decimal`` (nunca ``float``). Ver docs/05-interfaz-de-usuario.md §6.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLineEdit, QWidget

from ui.theme import ERROR_BACKGROUND, ERROR_COLOR
from utils.units import (
    INTERNAL_AREA_PER_M2,
    LengthError,
    Unit,
    area_internal_to_m2,
    format_length,
    mm_to_internal,
    parse_length,
)

ERROR_STYLE = f"border: 1px solid {ERROR_COLOR}; background: {ERROR_BACKGROUND};"


class UnitsDisplay(QObject):
    """Unidad visible compartida por todos los widgets. Emite ``unit_changed`` al cambiar."""

    unit_changed = Signal(object)

    def __init__(self, unit: Unit = Unit.MM, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._unit = unit

    @property
    def unit(self) -> Unit:
        return self._unit

    def set_unit(self, unit: Unit) -> None:
        if unit is not self._unit:
            self._unit = unit
            self.unit_changed.emit(unit)

    @property
    def symbol(self) -> str:
        return self._unit.symbol

    def format(self, value: int, *, with_unit: bool = False) -> str:
        """Unidades internas → texto en la unidad visible (``18300`` → ``"183"`` en cm)."""
        return format_length(value, self._unit, with_unit=with_unit)

    def parse(self, text: str, *, allow_zero: bool = False) -> int:
        """Texto en la unidad visible → unidades internas. Lanza ``LengthError``."""
        return mm_to_internal(parse_length(text, self._unit, allow_zero=allow_zero))


def parse_area_m2(text: str) -> int:
    """Área en m² introducida por el usuario → dmm². Lanza ``LengthError``."""
    clean = text.strip().replace(",", ".")
    try:
        value = Decimal(clean)
    except InvalidOperation as exc:
        raise LengthError(f"«{text}» no es un número válido") from exc
    if not value.is_finite() or value < 0:
        raise LengthError("El área debe ser un número mayor o igual que cero")
    scaled = value * INTERNAL_AREA_PER_M2
    if scaled != scaled.to_integral_value():
        raise LengthError("El área tiene demasiados decimales")
    return int(scaled)


def format_area_input(area: int) -> str:
    """dmm² → texto editable en m² (sin unidad, sin ceros sobrantes)."""
    text = f"{area_internal_to_m2(area):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


class LengthEdit(QLineEdit):
    """Campo de longitud: muestra en la unidad visible y guarda unidades internas.

    Al terminar la edición interpreta el texto; si es inválido lo marca en rojo con el
    motivo en el tooltip y conserva el último valor válido. Emite ``value_changed(int)``
    solo cuando el valor cambia.
    """

    value_changed = Signal(int)

    def __init__(
        self,
        units: UnitsDisplay,
        value: int = 0,
        *,
        allow_zero: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.units = units
        self.allow_zero = allow_zero
        self._value = value
        self._error: str | None = None
        self.editingFinished.connect(self._commit)
        units.unit_changed.connect(lambda _unit: self._refresh())
        self._refresh()

    def value(self) -> int:
        return self._value

    def set_value(self, value: int) -> None:
        """Fija el valor sin emitir ``value_changed``."""
        self._value = value
        self._set_error(None)
        self._refresh()

    @property
    def error(self) -> str | None:
        return self._error

    def _refresh(self) -> None:
        if self._error is None:
            self.setText(self.units.format(self._value))
        self.setPlaceholderText(self.units.symbol)
        self.setToolTip(self._error or f"Valor en {self.units.symbol}")

    def _set_error(self, message: str | None) -> None:
        self._error = message
        self.setStyleSheet(ERROR_STYLE if message else "")
        self.setToolTip(message or f"Valor en {self.units.symbol}")

    def _commit(self) -> None:
        try:
            value = self.units.parse(self.text(), allow_zero=self.allow_zero)
        except LengthError as exc:
            self._set_error(str(exc))
            return
        self._set_error(None)
        self.setText(self.units.format(value))
        if value != self._value:
            self._value = value
            self.value_changed.emit(value)
