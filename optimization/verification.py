"""Verificador independiente de resultados.

No confía en ningún algoritmo de colocación: recalcula los invariantes sobre las
coordenadas reales del resultado. Toda solución pasa por aquí antes de aceptarse.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from models.parametros import CutMode, CuttingParameters
from models.pieza import PieceInstance
from models.placa import PlateGrain
from models.resultado import OptimizationResult, SheetLayout
from optimization.guillotine import is_guillotine
from optimization.orientation import allowed_rotations
from utils.geometry import Rect


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    sheet_index: int | None = None


def verify_sheet(
    sheet: SheetLayout, params: CuttingParameters, grain: PlateGrain
) -> list[Violation]:
    out: list[Violation] = []
    m = sheet.edge_margin
    area = Rect(m, m, sheet.width - 2 * m, sheet.height - 2 * m)
    gap = params.cut_gap
    rects = []
    for p in sheet.placements:
        r = p.rect
        rects.append(r)
        label = p.piece.label
        if not area.contains(r):
            out.append(Violation("OUT_OF_BOUNDS", f"{label} sale del área útil: {r}", sheet.index))
        expected = (p.piece.height, p.piece.width) if p.rotated else (p.piece.width, p.piece.height)
        if (p.width, p.height) != expected:
            out.append(
                Violation(
                    "WRONG_SIZE",
                    f"{label}: medida colocada {p.width}×{p.height} ≠ {expected}",
                    sheet.index,
                )
            )
        allowed = allowed_rotations(p.piece.spec, grain, params.allow_rotation)
        if p.rotated not in allowed:
            out.append(
                Violation("BAD_ORIENTATION", f"{label}: orientación no permitida", sheet.index)
            )
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            sep = rects[i].separation(rects[j])
            if sep < gap:
                a, b = sheet.placements[i].piece.label, sheet.placements[j].piece.label
                code = "OVERLAP" if sep < 0 else "KERF"
                out.append(
                    Violation(code, f"{a} y {b}: separación {sep} < {gap} (dmm)", sheet.index)
                )
    if params.cut_mode is CutMode.PANEL_SAW and rects:
        if not is_guillotine(rects, Rect(0, 0, sheet.width, sheet.height), params.kerf):
            out.append(
                Violation(
                    "NOT_GUILLOTINE", "La placa no se puede cortar en guillotina", sheet.index
                )
            )
    return out


def verify_result(
    result: OptimizationResult,
    pieces: Iterable[PieceInstance],
    grain: PlateGrain,
) -> list[Violation]:
    """Invariantes de todo el resultado, incluida la conservación de piezas."""
    out: list[Violation] = []
    for sheet in result.sheets:
        out.extend(verify_sheet(sheet, result.params, grain))
    expected = Counter(p.uid for p in pieces)
    got = Counter(p.piece.uid for p in result.placements) + Counter(
        u.piece.uid for u in result.unplaced
    )
    if expected != got:
        missing = sorted((expected - got).elements())
        extra = sorted((got - expected).elements())
        out.append(
            Violation("CONSERVATION", f"Piezas perdidas {missing} / duplicadas o ajenas {extra}")
        )
    return out
