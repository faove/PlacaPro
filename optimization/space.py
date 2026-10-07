"""Espacio de empaquetado: transformación de placas y piezas para modelar kerf y margen.

Todo en unidades internas (dmm). Con ``gap = kerf + separación adicional``:

* Área útil en el espacio de empaquetado: ``W_u = W − 2·margen + gap`` (ídem alto).
* Pieza inflada: ``w' = w + gap`` (ídem alto).
* Coordenada real = coordenada de empaquetado + margen.

Así, entre dos piezas contiguas queda exactamente ``gap``, y la última pieza de una
fila termina como máximo en ``W − margen``: el kerf sobrante cae en el margen.
Ver docs/04-plan-de-corte-fisico.md §2.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from models.parametros import CuttingParameters
from models.pieza import PieceInstance
from models.placa import PlateFormat, PlateGrain
from models.resultado import SheetSource
from models.retazo import Offcut
from optimization.orientation import allowed_rotations, oriented_size


@dataclass(frozen=True)
class BinSpec:
    """Una placa (o retazo) disponible para colocar piezas."""

    width: int
    height: int
    thickness: int
    source: SheetSource
    margin: int
    grain: PlateGrain = PlateGrain.NONE
    plate_format_id: int | None = None
    offcut_id: int | None = None

    def packing_size(self, gap: int) -> tuple[int, int]:
        return (self.width - 2 * self.margin + gap, self.height - 2 * self.margin + gap)

    @property
    def is_full_plate(self) -> bool:
        return self.source is not SheetSource.OFFCUT

    @classmethod
    def from_plate(
        cls, plate: PlateFormat, params: CuttingParameters, source: SheetSource = SheetSource.NEW
    ) -> BinSpec:
        return cls(
            plate.width,
            plate.height,
            plate.thickness,
            source,
            params.edge_margin,
            plate.grain,
            plate.id,
        )

    @classmethod
    def from_offcut(cls, offcut: Offcut, params: CuttingParameters, grain: PlateGrain) -> BinSpec:
        """Retazo del stock: solo se refila si ``needs_trim``."""
        return cls(
            offcut.width,
            offcut.height,
            offcut.thickness,
            SheetSource.OFFCUT,
            params.edge_margin if offcut.needs_trim else 0,
            grain,
            offcut.plate_format_id,
            offcut.id,
        )


def piece_rotations(
    piece: PieceInstance, grain: PlateGrain, params: CuttingParameters
) -> tuple[bool, ...]:
    """Orientaciones permitidas, sin duplicar la rotada si la pieza es cuadrada."""
    rotations = allowed_rotations(piece.spec, grain, params.allow_rotation)
    if piece.width == piece.height and len(rotations) > 1:
        return rotations[:1]
    return rotations


def fits_in_bin(
    piece: PieceInstance, rotations: tuple[bool, ...], bin_spec: BinSpec, gap: int
) -> bool:
    bw, bh = bin_spec.packing_size(gap)
    return any(
        w + gap <= bw and h + gap <= bh
        for w, h in (oriented_size(piece.width, piece.height, r) for r in rotations)
    )


def lower_bound(pieces: Iterable[PieceInstance], bin_spec: BinSpec, gap: int) -> int:
    """Cota inferior de placas: ⌈Σ área inflada / área útil⌉ (sin contar retazos)."""
    bw, bh = bin_spec.packing_size(gap)
    capacity = bw * bh
    total = sum((p.width + gap) * (p.height + gap) for p in pieces)
    if total == 0 or capacity <= 0:
        return 0
    return -(-total // capacity)
