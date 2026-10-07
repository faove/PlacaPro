"""Utilidades compartidas por los tests del optimizador."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from models.parametros import CuttingParameters, OptimizationLevel
from models.pieza import PieceSpec, expand_pieces
from models.placa import PlateFormat
from models.plan_corte import CutOrientation, CutPlan
from models.resultado import OptimizationResult, SheetLayout
from optimization.optimizer import OptimizationRequest, Optimizer
from optimization.verification import verify_result
from utils.geometry import Rect
from utils.units import mm_to_internal


def params_mm(kerf="3.2", margin="10", spacing="0", **kw) -> CuttingParameters:
    return CuttingParameters(
        kerf=mm_to_internal(kerf),
        edge_margin=mm_to_internal(margin),
        extra_spacing=mm_to_internal(spacing),
        **kw,
    )


def run(
    specs: list[PieceSpec],
    plate: PlateFormat,
    params: CuttingParameters | None = None,
    *,
    level: OptimizationLevel = OptimizationLevel.BALANCED,
    stock_plates: int = 0,
    offcuts=(),
) -> OptimizationResult:
    """Optimiza y exige que el verificador independiente no encuentre violaciones."""
    params = replace(params or params_mm(), level=level)
    pieces = expand_pieces(specs)
    result = Optimizer(
        OptimizationRequest(pieces, plate, params, stock_plates, offcuts), time_budget_s=60
    ).run()
    violations = verify_result(result, pieces, plate.grain)
    assert violations == [], violations
    return result


def piece(name: str, qty: int, w, h, t=18, **kw) -> PieceSpec:
    return PieceSpec.from_mm(name, qty, w, h, t, **kw)


def plate_mm(w, h, t=18, **kw) -> PlateFormat:
    return PlateFormat.from_mm("Placa", w, h, t, **kw)


def simulate_cuts(width: int, height: int, plan: CutPlan, kerf: int) -> tuple[list[Rect], int]:
    """Simulador de taller, independiente del planificador.

    Parte de la placa entera y aplica cada corte, en orden, al único trozo que la sierra
    atraviesa de borde a borde; el corte se lleva ``kerf`` de material (o lo que quede si
    el trozo es más estrecho). Devuelve los trozos finales y el área convertida en serrín.
    Falla si un corte no atraviesa exactamente un trozo o si la medida de tope no coincide.
    """
    pieces = [Rect(0, 0, width, height)]
    sawdust = 0
    for cut in plan.cuts:
        vertical = cut.orientation is CutOrientation.VERTICAL
        p = cut.position

        if vertical:
            hits = [
                r
                for r in pieces
                if r.y == cut.start and r.h == cut.length and p < r.right and p + max(kerf, 1) > r.x
            ]
        else:
            hits = [
                r
                for r in pieces
                if r.x == cut.start
                and r.w == cut.length
                and p < r.bottom
                and p + max(kerf, 1) > r.y
            ]
        assert len(hits) == 1, f"el corte {cut.order} atraviesa {len(hits)} trozos"
        r = hits[0]
        pieces.remove(r)
        lo, hi = (r.x, r.right) if vertical else (r.y, r.bottom)
        assert cut.fence_distance == max(p - lo, 0), f"tope del corte {cut.order}"
        a_end, b_start = max(p, lo), min(p + kerf, hi)
        removed = b_start - a_end
        assert removed == cut.kerf and (removed > 0 or kerf == 0), f"kerf del corte {cut.order}"
        sawdust += removed * cut.length
        if vertical:
            parts = [Rect(lo, r.y, a_end - lo, r.h), Rect(b_start, r.y, hi - b_start, r.h)]
        else:
            parts = [Rect(r.x, lo, r.w, a_end - lo), Rect(r.x, b_start, r.w, hi - b_start)]
        pieces.extend(q for q in parts if not q.is_empty)
    return pieces, sawdust


def assert_plan_reconstructs(sheet: SheetLayout, params: CuttingParameters) -> None:
    """La secuencia de cortes produce exactamente las piezas y los sobrantes de la placa,
    y las áreas cuadran: piezas + kerf + retazos + desperdicio = área de la placa."""
    plan = sheet.cut_plan
    assert plan is not None
    parts, sawdust = simulate_cuts(sheet.width, sheet.height, plan, params.kerf)
    expected = [p.rect for p in sheet.placements] + [
        Rect(o.x, o.y, o.width, o.height) for o in sheet.offcuts
    ]
    assert Counter(parts) == Counter(expected)
    assert sawdust == plan.kerf_area == sheet.kerf_area
    offcut_area = sum(o.area for o in sheet.offcuts)
    assert sheet.used_area + sheet.kerf_area + offcut_area == sheet.total_area
    levels = [c.level for c in plan.cuts]
    assert levels == sorted(levels)
    assert [c.order for c in plan.cuts] == list(range(1, len(plan.cuts) + 1))
