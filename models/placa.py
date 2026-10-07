"""Placas (formatos de tablero), materiales, proveedores y stock.

Las medidas se guardan en unidades internas (décimas de mm, ``int``).
Use ``PlateFormat.from_mm(...)`` para construir desde milímetros.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from models._base import require_int
from utils.geometry import Rect
from utils.units import format_length, internal_to_mm, mm_to_internal


class PlateGrain(Enum):
    """Dirección de la veta de la placa."""

    ALONG_HEIGHT = "along_height"
    """Veta paralela al alto de la placa (lo habitual: a lo largo del lado mayor)."""
    ALONG_WIDTH = "along_width"
    NONE = "none"
    """Placa lisa o sin dibujo (p. ej. melamina blanca)."""

    @property
    def label(self) -> str:
        return {
            PlateGrain.ALONG_HEIGHT: "A lo largo del alto",
            PlateGrain.ALONG_WIDTH: "A lo largo del ancho",
            PlateGrain.NONE: "Sin veta",
        }[self]


class MaterialKind(Enum):
    MELAMINA = "melamina"
    MDF = "mdf"
    FENOLICO = "fenolico"
    MADERA_MACIZA = "madera_maciza"
    AGLOMERADO = "aglomerado"
    OTRO = "otro"

    @property
    def label(self) -> str:
        return {
            MaterialKind.MELAMINA: "Melamina",
            MaterialKind.MDF: "MDF",
            MaterialKind.FENOLICO: "Fenólico",
            MaterialKind.MADERA_MACIZA: "Madera maciza",
            MaterialKind.AGLOMERADO: "Aglomerado",
            MaterialKind.OTRO: "Otro",
        }[self]


@dataclass(frozen=True)
class Material:
    name: str
    kind: MaterialKind = MaterialKind.MELAMINA
    notes: str = ""
    id: int | None = None


@dataclass(frozen=True)
class Supplier:
    name: str
    contact: str = ""
    id: int | None = None


@dataclass(frozen=True)
class PlateFormat:
    """Formato de placa: dimensiones nominales y datos comerciales."""

    name: str
    width: int
    height: int
    thickness: int
    material_id: int | None = None
    color: str = ""
    supplier_id: int | None = None
    grain: PlateGrain = PlateGrain.NONE
    price_cents: int | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("width", "height", "thickness"):
            require_int(field_name, getattr(self, field_name))

    @classmethod
    def from_mm(
        cls,
        name: str,
        width_mm: Decimal | int | str,
        height_mm: Decimal | int | str,
        thickness_mm: Decimal | int | str,
        **kwargs: object,
    ) -> PlateFormat:
        return cls(
            name,
            mm_to_internal(width_mm),
            mm_to_internal(height_mm),
            mm_to_internal(thickness_mm),
            **kwargs,  # type: ignore[arg-type]
        )

    @property
    def width_mm(self) -> Decimal:
        return internal_to_mm(self.width)

    @property
    def height_mm(self) -> Decimal:
        return internal_to_mm(self.height)

    @property
    def thickness_mm(self) -> Decimal:
        return internal_to_mm(self.thickness)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def dimensions_label(self) -> str:
        """Ej.: ``"1830 × 2820 × 18 mm"``."""
        w, h, t = (format_length(v) for v in (self.width, self.height, self.thickness))
        return f"{w} × {h} × {t} mm"

    def usable_rect(self, edge_margin: int) -> Rect:
        """Región dentro de los márgenes de refilado (coordenadas reales de la placa)."""
        require_int("edge_margin", edge_margin)
        return Rect(
            edge_margin,
            edge_margin,
            max(self.width - 2 * edge_margin, 0),
            max(self.height - 2 * edge_margin, 0),
        )


@dataclass(frozen=True)
class StockPlate:
    """Cantidad disponible en inventario de un formato de placa."""

    plate_format_id: int
    quantity: int
