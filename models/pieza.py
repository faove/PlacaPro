"""Piezas: definición con cantidad (``PieceSpec``) e instancias individuales (``PieceInstance``)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from models._base import require_int
from utils.units import format_length, internal_to_mm, mm_to_internal


class GrainDirection(Enum):
    """Veta de la pieza, referida a sus propias dimensiones."""

    VERTICAL = "vertical"
    """Veta paralela al ALTO de la pieza."""
    HORIZONTAL = "horizontal"
    """Veta paralela al ANCHO de la pieza."""
    NONE = "none"
    """Indiferente."""

    @property
    def label(self) -> str:
        return {
            GrainDirection.VERTICAL: "Veta vertical",
            GrainDirection.HORIZONTAL: "Veta horizontal",
            GrainDirection.NONE: "Indiferente",
        }[self]


class PieceCategory(Enum):
    """Tipo de pieza. Determina el color en el diagrama."""

    LATERAL = "lateral"
    TAPA = "tapa"
    BASE = "base"
    FONDO = "fondo"
    PUERTA = "puerta"
    DIVISOR = "divisor"
    ESTANTE = "estante"
    CAJON = "cajon"
    ZOCALO = "zocalo"
    OTRO = "otro"

    @property
    def label(self) -> str:
        return {
            PieceCategory.LATERAL: "Lateral",
            PieceCategory.TAPA: "Tapa",
            PieceCategory.BASE: "Base",
            PieceCategory.FONDO: "Fondo",
            PieceCategory.PUERTA: "Puerta",
            PieceCategory.DIVISOR: "Divisor",
            PieceCategory.ESTANTE: "Estante",
            PieceCategory.CAJON: "Cajón",
            PieceCategory.ZOCALO: "Zócalo",
            PieceCategory.OTRO: "Otro",
        }[self]


@dataclass(frozen=True)
class PieceSpec:
    """Pieza tal como la define el usuario, con cantidad.

    Solo se comprueban los tipos; las reglas (cantidad ≥ 1, medidas > 0, que quepa
    en la placa...) las aplica ``models.validation`` para poder informar al usuario.
    """

    name: str
    quantity: int
    width: int
    height: int
    thickness: int
    category: PieceCategory = PieceCategory.OTRO
    material_id: int | None = None
    can_rotate: bool = True
    grain: GrainDirection = GrainDirection.NONE
    fixed_orientation: bool = False
    notes: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("quantity", "width", "height", "thickness"):
            require_int(field_name, getattr(self, field_name))

    @classmethod
    def from_mm(
        cls,
        name: str,
        quantity: int,
        width_mm: Decimal | int | str,
        height_mm: Decimal | int | str,
        thickness_mm: Decimal | int | str,
        **kwargs: Any,
    ) -> PieceSpec:
        return cls(
            name,
            quantity,
            mm_to_internal(width_mm),
            mm_to_internal(height_mm),
            mm_to_internal(thickness_mm),
            **kwargs,
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
        """Área de UNA pieza en dmm²."""
        return self.width * self.height

    @property
    def total_area(self) -> int:
        return self.area * max(self.quantity, 0)

    @property
    def dimensions_label(self) -> str:
        return f"{format_length(self.width)} × {format_length(self.height)}"

    def expand(self, first_uid: int = 1) -> list[PieceInstance]:
        """Convierte la cantidad en instancias individuales numeradas 1..cantidad."""
        return [PieceInstance(self, i, first_uid + i - 1) for i in range(1, self.quantity + 1)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "quantity": self.quantity,
            "width": self.width,
            "height": self.height,
            "thickness": self.thickness,
            "category": self.category.value,
            "material_id": self.material_id,
            "can_rotate": self.can_rotate,
            "grain": self.grain.value,
            "fixed_orientation": self.fixed_orientation,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PieceSpec:
        return cls(
            name=data["name"],
            quantity=data["quantity"],
            width=data["width"],
            height=data["height"],
            thickness=data["thickness"],
            category=PieceCategory(data.get("category", "otro")),
            material_id=data.get("material_id"),
            can_rotate=bool(data.get("can_rotate", True)),
            grain=GrainDirection(data.get("grain", "none")),
            fixed_orientation=bool(data.get("fixed_orientation", False)),
            notes=data.get("notes", ""),
            id=data.get("id"),
        )


@dataclass(frozen=True)
class PieceInstance:
    """Una pieza física concreta (p. ej. el segundo lateral).

    ``uid`` es único dentro de una optimización; ``index`` es 1..cantidad dentro de su spec.
    """

    spec: PieceSpec
    index: int
    uid: int

    @property
    def label(self) -> str:
        """``"Lateral 2"`` si la pieza tiene cantidad > 1; si no, solo el nombre."""
        return f"{self.spec.name} {self.index}" if self.spec.quantity > 1 else self.spec.name

    @property
    def width(self) -> int:
        return self.spec.width

    @property
    def height(self) -> int:
        return self.spec.height

    @property
    def area(self) -> int:
        return self.spec.area


def expand_pieces(specs: Iterable[PieceSpec]) -> list[PieceInstance]:
    """Expande todas las specs a instancias con ``uid`` consecutivos desde 1."""
    instances: list[PieceInstance] = []
    for spec in specs:
        instances.extend(spec.expand(first_uid=len(instances) + 1))
    return instances
