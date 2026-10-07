"""Conversión y formateo de unidades de longitud.

Convenciones (ver docs/01-arquitectura.md, ADR-002):

* El dominio expresa longitudes en **milímetros** como ``Decimal``.
* El núcleo geométrico trabaja con **enteros en décimas de milímetro**
  ("unidades internas", sufijo ``_dmm``): 1830 mm -> 18300.
* La precisión máxima admitida es 0,1 mm. Cualquier valor más fino se rechaza
  en lugar de redondearse silenciosamente.
* Nunca se usa ``float`` para longitudes.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum

INTERNAL_PER_MM = 10
"""Unidades internas por milímetro (décimas de mm)."""

INTERNAL_AREA_PER_M2 = (1000 * INTERNAL_PER_MM) ** 2
"""Unidades internas de área (dmm²) por metro cuadrado."""


class LengthError(ValueError):
    """Valor de longitud inválido (formato, signo o precisión)."""


class Unit(Enum):
    """Unidades de visualización/entrada. El factor es mm por unidad."""

    MM = ("mm", Decimal(1))
    CM = ("cm", Decimal(10))
    M = ("m", Decimal(1000))

    def __init__(self, symbol: str, mm_per_unit: Decimal) -> None:
        self.symbol = symbol
        self.mm_per_unit = mm_per_unit

    @property
    def display_decimals(self) -> int:
        """Decimales necesarios para mostrar 0,1 mm exactos en esta unidad."""
        return {Unit.MM: 1, Unit.CM: 2, Unit.M: 4}[self]


def _to_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(
            f"Las longitudes no pueden ser {type(value).__name__}; use Decimal, int o str"
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            raise LengthError("El valor está vacío")
        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise LengthError(f"«{value}» no es un número válido") from exc
        if not result.is_finite():
            raise LengthError(f"«{value}» no es un número finito")
        return result
    raise TypeError(f"Tipo de longitud no soportado: {type(value).__name__}")


def mm_to_internal(value_mm: Decimal | int | str) -> int:
    """Convierte milímetros a unidades internas (décimas de mm) sin pérdida.

    Lanza ``LengthError`` si el valor tiene más precisión que 0,1 mm.
    """
    scaled = _to_decimal(value_mm) * INTERNAL_PER_MM
    if scaled != scaled.to_integral_value():
        raise LengthError(f"{value_mm} mm tiene más de 1 decimal (precisión máxima 0,1 mm)")
    return int(scaled)


def internal_to_mm(value: int) -> Decimal:
    """Convierte unidades internas a milímetros exactos."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Las unidades internas deben ser int")
    return Decimal(value).scaleb(-1)


def to_unit(value: int, unit: Unit) -> Decimal:
    """Convierte unidades internas a la unidad de visualización indicada (exacto)."""
    return internal_to_mm(value) / unit.mm_per_unit


def parse_length(
    text: str | Decimal | int, unit: Unit = Unit.MM, *, allow_zero: bool = False
) -> Decimal:
    """Interpreta una longitud introducida por el usuario y la devuelve en mm.

    Acepta coma o punto decimal. Rechaza negativos, cero (salvo ``allow_zero``)
    y valores con precisión mayor a 0,1 mm una vez convertidos a mm.
    """
    value_mm = _to_decimal(text) * unit.mm_per_unit
    if value_mm < 0:
        raise LengthError("La longitud no puede ser negativa")
    if value_mm == 0 and not allow_zero:
        raise LengthError("La longitud debe ser mayor que cero")
    mm_to_internal(value_mm)  # valida la precisión
    return value_mm


def _format_decimal(value: Decimal, decimals: int, decimal_sep: str, trim: bool) -> str:
    text = f"{value:.{decimals}f}"
    if trim and "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    return text.replace(".", decimal_sep)


def format_length(
    value: int,
    unit: Unit = Unit.MM,
    *,
    decimals: int | None = None,
    with_unit: bool = False,
    decimal_sep: str = ",",
    trim: bool = True,
) -> str:
    """Formatea unidades internas en la unidad pedida.

    Por defecto muestra la precisión exacta (0,1 mm) sin ceros sobrantes:
    ``format_length(18300) == "1830"``, ``format_length(32) == "3,2"``.
    """
    places = unit.display_decimals if decimals is None else decimals
    text = _format_decimal(to_unit(value, unit), places, decimal_sep, trim)
    return f"{text} {unit.symbol}" if with_unit else text


def area_internal_to_m2(area: int) -> Decimal:
    """Convierte un área en dmm² a m² exactos."""
    if isinstance(area, bool) or not isinstance(area, int):
        raise TypeError("El área interna debe ser int")
    return Decimal(area) / INTERNAL_AREA_PER_M2


def format_area_m2(
    area: int, *, decimals: int = 2, with_unit: bool = True, decimal_sep: str = ","
) -> str:
    """Formatea un área interna en m² (las áreas siempre se muestran en m²)."""
    text = _format_decimal(area_internal_to_m2(area), decimals, decimal_sep, trim=False)
    return f"{text} m²" if with_unit else text
