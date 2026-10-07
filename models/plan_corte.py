"""Plan de corte físico: secuencia de cortes para el taller (lo calcula el sprint 3)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from models.parametros import CutMode


class CutOrientation(Enum):
    HORIZONTAL = "horizontal"
    """Línea de corte paralela al eje X (separa arriba / abajo)."""
    VERTICAL = "vertical"
    """Línea de corte paralela al eje Y (separa izquierda / derecha)."""


@dataclass(frozen=True)
class Cut:
    """Un corte recto. Coordenadas en dmm, absolutas sobre la placa.

    ``position``: coordenada del inicio de la franja de kerf (Y si es horizontal, X si es
    vertical). ``start``/``length``: tramo que recorre la sierra. ``fence_distance``:
    medida a ajustar en el tope, desde el borde de referencia de la región que se corta.
    """

    order: int
    level: int
    orientation: CutOrientation
    position: int
    start: int
    length: int
    fence_distance: int
    is_trim: bool = False
    resulting: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "level": self.level,
            "orientation": self.orientation.value,
            "position": self.position,
            "start": self.start,
            "length": self.length,
            "fence_distance": self.fence_distance,
            "is_trim": self.is_trim,
            "resulting": list(self.resulting),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Cut:
        return cls(
            order=data["order"],
            level=data["level"],
            orientation=CutOrientation(data["orientation"]),
            position=data["position"],
            start=data["start"],
            length=data["length"],
            fence_distance=data["fence_distance"],
            is_trim=data.get("is_trim", False),
            resulting=tuple(data.get("resulting", ())),
        )


@dataclass(frozen=True)
class CutPlan:
    sheet_index: int
    cuts: tuple[Cut, ...] = ()
    mode: CutMode = CutMode.PANEL_SAW

    @property
    def cut_count(self) -> int:
        return len(self.cuts)

    @property
    def total_cut_length(self) -> int:
        return sum(c.length for c in self.cuts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet_index": self.sheet_index,
            "mode": self.mode.value,
            "cuts": [c.to_dict() for c in self.cuts],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CutPlan:
        return cls(
            sheet_index=data["sheet_index"],
            cuts=tuple(Cut.from_dict(c) for c in data.get("cuts", ())),
            mode=CutMode(data.get("mode", CutMode.PANEL_SAW.value)),
        )
