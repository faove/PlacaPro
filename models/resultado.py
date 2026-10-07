"""Resultado de una optimización: placas usadas, colocaciones, retazos y métricas.

Definición de áreas (docs/02-modelo-de-dominio-y-datos.md):

* área total = suma de las áreas nominales de las placas usadas;
* área utilizada = suma de las áreas netas de las piezas (sin kerf);
* desperdicio = total − utilizada (incluye kerf, márgenes y retazos);
* aprovechamiento = utilizada / total.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from models._base import dt_from_str, dt_to_str
from models.parametros import CuttingParameters
from models.pieza import PieceInstance, PieceSpec
from models.plan_corte import CutPlan
from models.retazo import Offcut, OffcutStatus
from utils.geometry import Rect


class SheetSource(Enum):
    NEW = "new"
    """Placa nueva (a comprar)."""
    STOCK = "stock"
    """Placa del inventario."""
    OFFCUT = "offcut"
    """Retazo del stock."""

    @property
    def label(self) -> str:
        return {
            SheetSource.NEW: "Nueva",
            SheetSource.STOCK: "Inventario",
            SheetSource.OFFCUT: "Retazo",
        }[self]


def _piece_to_dict(piece: PieceInstance) -> dict[str, Any]:
    return {"spec": piece.spec.to_dict(), "index": piece.index, "uid": piece.uid}


def _piece_from_dict(data: dict[str, Any]) -> PieceInstance:
    return PieceInstance(PieceSpec.from_dict(data["spec"]), data["index"], data["uid"])


@dataclass(frozen=True)
class Placement:
    """Pieza colocada. ``x``, ``y``, ``width``, ``height`` son reales (dmm) sobre la placa,
    ya girados si ``rotated`` es True."""

    piece: PieceInstance
    sheet_index: int
    x: int
    y: int
    width: int
    height: int
    rotated: bool = False

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.height)

    def to_dict(self) -> dict[str, Any]:
        return {
            "piece": _piece_to_dict(self.piece),
            "sheet_index": self.sheet_index,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotated": self.rotated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Placement:
        return cls(
            piece=_piece_from_dict(data["piece"]),
            sheet_index=data["sheet_index"],
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            rotated=data["rotated"],
        )


@dataclass(frozen=True)
class UnplacedPiece:
    piece: PieceInstance
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"piece": _piece_to_dict(self.piece), "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnplacedPiece:
        return cls(_piece_from_dict(data["piece"]), data["reason"])


@dataclass(frozen=True)
class SheetLayout:
    """Distribución de una placa."""

    index: int
    width: int
    height: int
    thickness: int
    source: SheetSource = SheetSource.NEW
    plate_format_id: int | None = None
    source_offcut_id: int | None = None
    placements: tuple[Placement, ...] = ()
    offcuts: tuple[Offcut, ...] = ()
    cut_plan: CutPlan | None = None
    edge_margin: int = 0
    """Refilado aplicado a esta placa (0 en retazos ya escuadrados)."""

    @property
    def total_area(self) -> int:
        return self.width * self.height

    @property
    def used_area(self) -> int:
        return sum(p.width * p.height for p in self.placements)

    @property
    def waste_area(self) -> int:
        return self.total_area - self.used_area

    @property
    def reusable_offcut_area(self) -> int:
        return sum(o.area for o in self.offcuts if o.status is OffcutStatus.REUSABLE)

    @property
    def unusable_waste_area(self) -> int:
        return self.waste_area - self.reusable_offcut_area

    @property
    def utilization(self) -> float:
        """Fracción 0..1 (solo para mostrar; los cálculos usan las áreas enteras)."""
        return self.used_area / self.total_area if self.total_area else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "width": self.width,
            "height": self.height,
            "thickness": self.thickness,
            "source": self.source.value,
            "plate_format_id": self.plate_format_id,
            "source_offcut_id": self.source_offcut_id,
            "placements": [p.to_dict() for p in self.placements],
            "offcuts": [o.to_dict() for o in self.offcuts],
            "cut_plan": self.cut_plan.to_dict() if self.cut_plan else None,
            "edge_margin": self.edge_margin,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SheetLayout:
        return cls(
            index=data["index"],
            width=data["width"],
            height=data["height"],
            thickness=data["thickness"],
            source=SheetSource(data.get("source", "new")),
            plate_format_id=data.get("plate_format_id"),
            source_offcut_id=data.get("source_offcut_id"),
            placements=tuple(Placement.from_dict(p) for p in data.get("placements", ())),
            offcuts=tuple(Offcut.from_dict(o) for o in data.get("offcuts", ())),
            cut_plan=CutPlan.from_dict(data["cut_plan"]) if data.get("cut_plan") else None,
            edge_margin=data.get("edge_margin", 0),
        )


@dataclass(frozen=True)
class OptimizationResult:
    params: CuttingParameters
    sheets: tuple[SheetLayout, ...] = ()
    unplaced: tuple[UnplacedPiece, ...] = ()
    strategy: str = ""
    score: tuple[int, ...] = ()
    lower_bound: int = 0
    duration_ms: int = 0
    project_id: int | None = None
    created_at: datetime | None = None
    id: int | None = None

    @property
    def sheets_count(self) -> int:
        return len(self.sheets)

    @property
    def total_area(self) -> int:
        return sum(s.total_area for s in self.sheets)

    @property
    def used_area(self) -> int:
        return sum(s.used_area for s in self.sheets)

    @property
    def waste_area(self) -> int:
        return self.total_area - self.used_area

    @property
    def reusable_offcut_area(self) -> int:
        return sum(s.reusable_offcut_area for s in self.sheets)

    @property
    def utilization(self) -> float:
        return self.used_area / self.total_area if self.total_area else 0.0

    @property
    def placements(self) -> list[Placement]:
        return [p for s in self.sheets for p in s.placements]

    @property
    def pieces_count(self) -> int:
        return len(self.placements)

    @property
    def is_complete(self) -> bool:
        return not self.unplaced

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "created_at": dt_to_str(self.created_at),
            "params": self.params.to_dict(),
            "sheets": [s.to_dict() for s in self.sheets],
            "unplaced": [u.to_dict() for u in self.unplaced],
            "strategy": self.strategy,
            "score": list(self.score),
            "lower_bound": self.lower_bound,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimizationResult:
        return cls(
            params=CuttingParameters.from_dict(data["params"]),
            sheets=tuple(SheetLayout.from_dict(s) for s in data.get("sheets", ())),
            unplaced=tuple(UnplacedPiece.from_dict(u) for u in data.get("unplaced", ())),
            strategy=data.get("strategy", ""),
            score=tuple(data.get("score", ())),
            lower_bound=data.get("lower_bound", 0),
            duration_ms=data.get("duration_ms", 0),
            project_id=data.get("project_id"),
            created_at=dt_from_str(data.get("created_at")),
            id=data.get("id"),
        )
