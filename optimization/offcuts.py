"""Sobrantes de una placa: fusión y clasificación en retazo reutilizable o desperdicio.

Los sobrantes son las hojas vacías del árbol de cortes (``guillotine.py``): rectángulos
exactos, ya descontado el kerf. Dos sobrantes alineados y separados solo por un corte
se fusionan si la placa sigue siendo guillotinable con el rectángulo unido: es un corte
menos y un retazo mayor. Ver docs/04-plan-de-corte-fisico.md §5.
"""

from __future__ import annotations

from collections.abc import Sequence

from models.parametros import CuttingParameters
from models.retazo import OffcutStatus
from optimization.guillotine import decompose
from utils.geometry import Rect


def classify(rect: Rect, params: CuttingParameters) -> OffcutStatus:
    """``REUSABLE`` si alcanza los mínimos de ancho, alto y área; si no, ``WASTE``.

    Los mínimos de ancho y alto se aceptan en cualquiera de las dos orientaciones: un
    retazo se puede girar al guardarlo.
    """
    lo, hi = sorted((rect.w, rect.h))
    min_lo, min_hi = sorted((params.min_offcut_width, params.min_offcut_height))
    if lo >= min_lo and hi >= min_hi and rect.area >= params.min_offcut_area:
        return OffcutStatus.REUSABLE
    return OffcutStatus.WASTE


def _union(a: Rect, b: Rect, kerf: int) -> Rect | None:
    """Rectángulo formado por ``a``, ``b`` y la franja de corte que los separa, o ``None``."""
    if a.y == b.y and a.h == b.h:
        left, right = (a, b) if a.x <= b.x else (b, a)
        if 0 <= right.x - left.right <= kerf:
            return Rect(left.x, a.y, right.right - left.x, a.h)
    if a.x == b.x and a.w == b.w:
        top, bottom = (a, b) if a.y <= b.y else (b, a)
        if 0 <= bottom.y - top.bottom <= kerf:
            return Rect(a.x, top.y, a.w, bottom.bottom - top.y)
    return None


def merge_offcuts(
    pieces: Sequence[Rect], leftovers: Sequence[Rect], region: Rect, kerf: int
) -> list[Rect]:
    """Fusiona sobrantes adyacentes mientras la placa siga siendo cortable.

    Se prueba primero la fusión que da el rectángulo mayor; una fusión se acepta si la
    distribución (piezas + sobrantes, estos como si fueran piezas) sigue siendo
    guillotinable y no necesita más cortes.
    """
    current = list(leftovers)
    base = decompose([*pieces, *current], region, kerf)
    if base is None:
        return current
    cuts = base.cut_count
    merged = True
    while merged:
        merged = False
        candidates: list[tuple[int, int, int, Rect]] = []
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                u = _union(current[i], current[j], kerf)
                if u is not None and not any(u.intersects(p) for p in pieces):
                    candidates.append((-u.area, i, j, u))
        for _, i, j, u in sorted(candidates, key=lambda c: c[:3]):
            trial = [r for k, r in enumerate(current) if k not in (i, j)] + [u]
            decomp = decompose([*pieces, *trial], region, kerf)
            if decomp is not None and decomp.cut_count <= cuts:
                current, cuts, merged = trial, decomp.cut_count, True
                break
    return current
