"""Utilidades compartidas por los tests del optimizador."""

from __future__ import annotations

from dataclasses import replace

from models.parametros import CuttingParameters, OptimizationLevel
from models.pieza import PieceSpec, expand_pieces
from models.placa import PlateFormat
from models.resultado import OptimizationResult
from optimization.optimizer import OptimizationRequest, Optimizer
from optimization.verification import verify_result
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
