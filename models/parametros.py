"""Parámetros de corte y de optimización (unidades internas)."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any

from models._base import require_int
from utils.constants import (
    DEFAULT_EDGE_MARGIN_MM,
    DEFAULT_EXTRA_SPACING_MM,
    DEFAULT_KERF_MM,
    DEFAULT_MIN_OFFCUT_AREA_M2,
    DEFAULT_MIN_OFFCUT_HEIGHT_MM,
    DEFAULT_MIN_OFFCUT_WIDTH_MM,
    DEFAULT_SEED,
)
from utils.units import INTERNAL_AREA_PER_M2, mm_to_internal


class OptimizationLevel(Enum):
    FAST = "fast"
    BALANCED = "balanced"
    MAX = "max"

    @property
    def label(self) -> str:
        return {
            OptimizationLevel.FAST: "Rápida",
            OptimizationLevel.BALANCED: "Equilibrada",
            OptimizationLevel.MAX: "Máxima",
        }[self]


class CutMode(Enum):
    PANEL_SAW = "panel_saw"
    """Escuadradora: solo layouts guillotinables."""
    CNC = "cnc"
    """Router CNC: se admiten layouts no guillotinables."""

    @property
    def label(self) -> str:
        return {CutMode.PANEL_SAW: "Escuadradora", CutMode.CNC: "CNC"}[self]


_INT_FIELDS = (
    "kerf",
    "edge_margin",
    "extra_spacing",
    "min_offcut_width",
    "min_offcut_height",
    "min_offcut_area",
    "seed",
)


@dataclass(frozen=True)
class CuttingParameters:
    """Parámetros de corte. Longitudes en dmm; ``min_offcut_area`` en dmm²."""

    kerf: int = mm_to_internal(DEFAULT_KERF_MM)
    edge_margin: int = mm_to_internal(DEFAULT_EDGE_MARGIN_MM)
    extra_spacing: int = mm_to_internal(DEFAULT_EXTRA_SPACING_MM)
    allow_rotation: bool = True
    level: OptimizationLevel = OptimizationLevel.BALANCED
    cut_mode: CutMode = CutMode.PANEL_SAW
    use_stock_first: bool = False
    use_offcuts_first: bool = False
    min_offcut_width: int = mm_to_internal(DEFAULT_MIN_OFFCUT_WIDTH_MM)
    min_offcut_height: int = mm_to_internal(DEFAULT_MIN_OFFCUT_HEIGHT_MM)
    min_offcut_area: int = int(DEFAULT_MIN_OFFCUT_AREA_M2 * INTERNAL_AREA_PER_M2)
    seed: int = DEFAULT_SEED

    def __post_init__(self) -> None:
        for name in _INT_FIELDS:
            require_int(name, getattr(self, name))

    @property
    def cut_gap(self) -> int:
        """Separación total entre piezas: kerf + separación adicional."""
        return self.kerf + self.extra_spacing

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            data[f.name] = value.value if isinstance(value, Enum) else value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CuttingParameters:
        """Tolerante a claves ausentes o desconocidas (compatibilidad entre versiones)."""
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if "level" in kwargs:
            kwargs["level"] = OptimizationLevel(kwargs["level"])
        if "cut_mode" in kwargs:
            kwargs["cut_mode"] = CutMode(kwargs["cut_mode"])
        return cls(**kwargs)
