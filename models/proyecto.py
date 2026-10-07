"""Proyectos y muebles.

Pipeline (docs/01-arquitectura.md): descripción del mueble → dimensiones → despiece
(``FurnitureGenerator``) → ``PieceSpec`` → instancias → optimizador.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from models._base import require_int
from models.parametros import CuttingParameters
from models.pieza import PieceInstance, PieceSpec, expand_pieces


@dataclass(frozen=True)
class FurnitureDimensions:
    """Medidas generales del mueble (dmm). Base para el futuro generador de despiece."""

    width: int
    height: int
    depth: int

    def __post_init__(self) -> None:
        for name in ("width", "height", "depth"):
            require_int(name, getattr(self, name))


@dataclass
class Furniture:
    """Un mueble dentro de un proyecto, con su lista de piezas."""

    name: str
    pieces: list[PieceSpec] = field(default_factory=list)
    dimensions: FurnitureDimensions | None = None
    generator_id: str = "manual"
    generator_params: dict[str, Any] = field(default_factory=dict)
    id: int | None = None


@dataclass
class Project:
    """Raíz de agregado: proyecto con sus muebles, placa elegida y parámetros."""

    name: str
    description: str = ""
    plate_format_id: int | None = None
    params: CuttingParameters = field(default_factory=CuttingParameters)
    furniture: list[Furniture] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: int | None = None

    def all_piece_specs(self) -> list[PieceSpec]:
        return [piece for item in self.furniture for piece in item.pieces]

    def piece_instances(self) -> list[PieceInstance]:
        return expand_pieces(self.all_piece_specs())

    @property
    def total_piece_count(self) -> int:
        return sum(max(p.quantity, 0) for p in self.all_piece_specs())

    def duplicate(self, new_name: str) -> Project:
        """Copia profunda sin identificadores ni fechas (lista para guardarse como nueva)."""
        clone = copy.deepcopy(self)
        clone.name = new_name
        clone.id = None
        clone.created_at = None
        clone.updated_at = None
        for item in clone.furniture:
            item.id = None
            item.pieces = [replace(p, id=None) for p in item.pieces]
        return clone
