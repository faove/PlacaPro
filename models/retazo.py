"""Retazos: sobrantes rectangulares de una placa."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from models._base import dt_from_str, dt_to_str, require_int
from utils.units import format_length


class OffcutStatus(Enum):
    REUSABLE = "reusable"
    """Sobrante de un resultado, suficientemente grande para reutilizar."""
    WASTE = "waste"
    """Sobrante no aprovechable."""
    IN_STOCK = "in_stock"
    """Guardado en el stock de retazos."""
    CONSUMED = "consumed"
    """Usado en una optimización posterior."""

    @property
    def label(self) -> str:
        return {
            OffcutStatus.REUSABLE: "Retazo reutilizable",
            OffcutStatus.WASTE: "Desperdicio",
            OffcutStatus.IN_STOCK: "En stock",
            OffcutStatus.CONSUMED: "Consumido",
        }[self]


@dataclass(frozen=True)
class Offcut:
    """Retazo. ``x``/``y`` solo tienen sentido dentro del resultado que lo generó."""

    width: int
    height: int
    thickness: int
    status: OffcutStatus
    plate_format_id: int | None = None
    material_id: int | None = None
    x: int | None = None
    y: int | None = None
    sheet_index: int | None = None
    source_result_id: int | None = None
    needs_trim: bool = False
    created_at: datetime | None = None
    notes: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        for name in ("width", "height", "thickness"):
            require_int(name, getattr(self, name))

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def dimensions_label(self) -> str:
        return f"{format_length(self.width)} × {format_length(self.height)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "width": self.width,
            "height": self.height,
            "thickness": self.thickness,
            "status": self.status.value,
            "plate_format_id": self.plate_format_id,
            "material_id": self.material_id,
            "x": self.x,
            "y": self.y,
            "sheet_index": self.sheet_index,
            "source_result_id": self.source_result_id,
            "needs_trim": self.needs_trim,
            "created_at": dt_to_str(self.created_at),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Offcut:
        return cls(
            width=data["width"],
            height=data["height"],
            thickness=data["thickness"],
            status=OffcutStatus(data["status"]),
            plate_format_id=data.get("plate_format_id"),
            material_id=data.get("material_id"),
            x=data.get("x"),
            y=data.get("y"),
            sheet_index=data.get("sheet_index"),
            source_result_id=data.get("source_result_id"),
            needs_trim=bool(data.get("needs_trim", False)),
            created_at=dt_from_str(data.get("created_at")),
            notes=data.get("notes", ""),
            id=data.get("id"),
        )
