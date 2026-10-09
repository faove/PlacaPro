"""Plan de corte físico: secuencia de cortes para el taller (``optimization/cutting.py``)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from models.parametros import CutMode
from utils.units import Unit, format_length


class CutOrientation(Enum):
    HORIZONTAL = "horizontal"
    """Línea de corte paralela al eje X (separa arriba / abajo)."""
    VERTICAL = "vertical"
    """Línea de corte paralela al eje Y (separa izquierda / derecha)."""


class PartKind(Enum):
    PIECE = "piece"
    OFFCUT = "offcut"
    """Retazo reutilizable."""
    WASTE = "waste"
    TRIM = "trim"
    """Franja de refilado."""
    STRIP = "strip"
    """Tira o sub-tira que se seguirá cortando."""


@dataclass(frozen=True)
class ReleasedPart:
    """Lo que libera un corte: pieza, retazo, desperdicio, refilado o tira (dmm)."""

    kind: PartKind
    label: str
    width: int
    height: int

    def describe(self, orientation: CutOrientation, unit: Unit = Unit.MM) -> str:
        """Texto para el operario en la unidad pedida («Lateral 1 (60 × 40)»).

        De una tira solo interesa el ancho que fija el tope: el ancho si el corte es
        vertical, el alto si es horizontal.
        """
        size = f"{format_length(self.width, unit)} × {format_length(self.height, unit)}"
        if self.kind is PartKind.PIECE:
            return f"{self.label} ({size})"
        if self.kind is PartKind.OFFCUT:
            return f"Retazo {self.label} ({size})"
        if self.kind is PartKind.WASTE:
            return f"Desperdicio ({size})"
        if self.kind is PartKind.TRIM:
            return "Refilado"
        measure = self.width if orientation is CutOrientation.VERTICAL else self.height
        return f"{self.label} ({format_length(measure, unit, with_unit=True)})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "label": self.label,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReleasedPart:
        return cls(PartKind(data["kind"]), data["label"], data["width"], data["height"])


@dataclass(frozen=True)
class Cut:
    """Un corte recto. Coordenadas en dmm, absolutas sobre la placa.

    ``position``: coordenada del inicio de la franja de kerf (Y si es horizontal, X si es
    vertical). ``start``/``length``: tramo que recorre la sierra. ``fence_distance``:
    medida a ajustar en el tope, desde el borde de referencia de la región que se corta.
    ``kerf``: ancho de material que se lleva este corte (menor que el kerf nominal solo
    en el refilado, si el margen es más estrecho que la hoja). ``region``: nombre de la
    región que se corta («Placa», «Tira A», «Tira A.2»…). ``parts``: lo que libera el
    corte, estructurado; ``resulting`` es su descripción en mm (resultados anteriores al
    sprint 6 solo tienen ``resulting``).
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
    kerf: int = 0
    region: str = ""
    parts: tuple[ReleasedPart, ...] = ()

    @property
    def kerf_area(self) -> int:
        return self.kerf * self.length

    def resulting_labels(self, unit: Unit = Unit.MM) -> list[str]:
        """Lo que libera el corte, con las medidas en ``unit``."""
        if not self.parts:
            return list(self.resulting)
        return [p.describe(self.orientation, unit) for p in self.parts]

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
            "kerf": self.kerf,
            "region": self.region,
            "parts": [p.to_dict() for p in self.parts],
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
            kerf=data.get("kerf", 0),
            region=data.get("region", ""),
            parts=tuple(ReleasedPart.from_dict(p) for p in data.get("parts", ())),
        )


@dataclass(frozen=True)
class PieceContour:
    """Contorno rectangular de una pieza para router CNC (base de G-code/DXF)."""

    label: str
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PieceContour:
        return cls(data["label"], data["x"], data["y"], data["width"], data["height"])


@dataclass(frozen=True)
class CutPlan:
    """Plan de una placa. En ``PANEL_SAW``, ``cuts`` es la secuencia de escuadradora; en
    ``CNC`` (distribución no guillotinable) no hay cortes y ``contours`` lista las piezas."""

    sheet_index: int
    cuts: tuple[Cut, ...] = ()
    mode: CutMode = CutMode.PANEL_SAW
    contours: tuple[PieceContour, ...] = ()

    @property
    def cut_count(self) -> int:
        return len(self.cuts)

    @property
    def total_cut_length(self) -> int:
        return sum(c.length for c in self.cuts)

    @property
    def kerf_area(self) -> int:
        """Material convertido en serrín por todos los cortes (dmm²)."""
        return sum(c.kerf_area for c in self.cuts)

    @property
    def cuts_by_level(self) -> dict[int, int]:
        """Número de cortes por nivel (0 = refilado)."""
        out: dict[int, int] = {}
        for c in self.cuts:
            out[c.level] = out.get(c.level, 0) + 1
        return dict(sorted(out.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet_index": self.sheet_index,
            "mode": self.mode.value,
            "cuts": [c.to_dict() for c in self.cuts],
            "contours": [c.to_dict() for c in self.contours],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CutPlan:
        return cls(
            sheet_index=data["sheet_index"],
            cuts=tuple(Cut.from_dict(c) for c in data.get("cuts", ())),
            mode=CutMode(data.get("mode", CutMode.PANEL_SAW.value)),
            contours=tuple(PieceContour.from_dict(c) for c in data.get("contours", ())),
        )
