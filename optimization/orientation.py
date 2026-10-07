"""Orientaciones permitidas de una pieza según veta y rotación.

Una orientación se representa con ``rotated: bool`` (False = como se dibujó, True = 90°).

Reglas (docs/03-algoritmo-de-optimizacion.md §3):

* ``fixed_orientation`` fuerza la orientación dibujada.
* Si la pieza tiene veta y la placa también, la veta **manda**: se elige la única
  orientación que alinea ambas, aunque la rotación esté desactivada (la rotación
  desactivada se refiere a piezas sin veta).
* Si la pieza tiene veta pero la placa no, se respeta la orientación dibujada.
* Sin veta: se puede girar si la pieza lo permite y la rotación global está activa.
"""

from __future__ import annotations

from models.pieza import GrainDirection, PieceSpec
from models.placa import PlateGrain

ORIENTATION_AS_DRAWN: tuple[bool, ...] = (False,)
ORIENTATION_ROTATED: tuple[bool, ...] = (True,)
ORIENTATION_ANY: tuple[bool, ...] = (False, True)


def grain_required_rotation(grain: GrainDirection, plate_grain: PlateGrain) -> bool | None:
    """Rotación necesaria para alinear la veta de la pieza con la de la placa.

    Devuelve ``None`` si la veta no impone nada (pieza o placa sin veta).
    """
    if grain is GrainDirection.NONE or plate_grain is PlateGrain.NONE:
        return None
    piece_along_height = grain is GrainDirection.VERTICAL
    plate_along_height = plate_grain is PlateGrain.ALONG_HEIGHT
    return piece_along_height != plate_along_height


def allowed_rotations(
    spec: PieceSpec, plate_grain: PlateGrain, allow_rotation: bool = True
) -> tuple[bool, ...]:
    """Orientaciones (``rotated``) admisibles para ``spec`` en una placa con ``plate_grain``."""
    if spec.fixed_orientation:
        return ORIENTATION_AS_DRAWN
    if spec.grain is not GrainDirection.NONE:
        required = grain_required_rotation(spec.grain, plate_grain)
        return ORIENTATION_ROTATED if required else ORIENTATION_AS_DRAWN
    if spec.can_rotate and allow_rotation:
        return ORIENTATION_ANY
    return ORIENTATION_AS_DRAWN


def oriented_size(width: int, height: int, rotated: bool) -> tuple[int, int]:
    return (height, width) if rotated else (width, height)
