"""El verificador debe detectar cada tipo de error en resultados corrompidos a propósito."""

from dataclasses import replace

import pytest

from models.parametros import CutMode, CuttingParameters
from models.pieza import GrainDirection, PieceSpec
from models.placa import PlateGrain
from models.resultado import OptimizationResult, Placement, SheetLayout
from optimization.verification import verify_result

PARAMS = CuttingParameters(kerf=32, edge_margin=100)


def make(placements, params=PARAMS, width=18300, height=28200):
    sheet = SheetLayout(0, width, height, 180, placements=tuple(placements), edge_margin=100)
    return OptimizationResult(params, (sheet,))


def instance(w=4000, h=6000, uid=1, **kw):
    return PieceSpec("P", 1, w, h, 180, **kw).expand(first_uid=uid)[0]


def codes(result, pieces, grain=PlateGrain.NONE):
    return {v.code for v in verify_result(result, pieces, grain)}


def test_valid_result_has_no_violations():
    a, b = instance(uid=1), instance(uid=2)
    result = make([Placement(a, 0, 100, 100, 4000, 6000), Placement(b, 0, 4132, 100, 4000, 6000)])
    assert codes(result, [a, b]) == set()


def test_overlap_detected():
    a, b = instance(uid=1), instance(uid=2)
    result = make([Placement(a, 0, 100, 100, 4000, 6000), Placement(b, 0, 2000, 100, 4000, 6000)])
    assert "OVERLAP" in codes(result, [a, b])


def test_missing_kerf_detected():
    a, b = instance(uid=1), instance(uid=2)
    result = make([Placement(a, 0, 100, 100, 4000, 6000), Placement(b, 0, 4131, 100, 4000, 6000)])
    assert {"KERF", "NOT_GUILLOTINE"} <= codes(result, [a, b])  # la sierra no pasa


@pytest.mark.parametrize("x", [99, 18300 - 100 - 4000 + 1])
def test_margin_violation_detected(x):
    a = instance()
    assert "OUT_OF_BOUNDS" in codes(make([Placement(a, 0, x, 100, 4000, 6000)]), [a])


def test_wrong_size_detected():
    a = instance()
    assert "WRONG_SIZE" in codes(make([Placement(a, 0, 100, 100, 4000, 5999)]), [a])
    # girada pero con medidas sin intercambiar
    assert "WRONG_SIZE" in codes(make([Placement(a, 0, 100, 100, 4000, 6000, True)]), [a])


def test_grain_violation_detected():
    a = instance(grain=GrainDirection.VERTICAL)
    rotated = make([Placement(a, 0, 100, 100, 6000, 4000, True)])
    assert "BAD_ORIENTATION" in codes(rotated, [a], PlateGrain.ALONG_HEIGHT)
    # una pieza cuadrada con veta también cambia de veta al girarse
    sq = instance(5000, 5000, grain=GrainDirection.VERTICAL)
    assert "BAD_ORIENTATION" in codes(
        make([Placement(sq, 0, 100, 100, 5000, 5000, True)]), [sq], PlateGrain.ALONG_HEIGHT
    )


def test_conservation_detected():
    a, b = instance(uid=1), instance(uid=2)
    lost = make([Placement(a, 0, 100, 100, 4000, 6000)])
    assert "CONSERVATION" in codes(lost, [a, b])
    duplicated = make(
        [Placement(a, 0, 100, 100, 4000, 6000), Placement(a, 0, 4132, 100, 4000, 6000)]
    )
    assert "CONSERVATION" in codes(duplicated, [a])


def test_non_guillotine_detected_only_in_panel_saw_mode():
    s = 1000
    raw = [
        (0, 0, 2 * s, s),
        (2 * s + 32, 0, s, 2 * s),
        (s + 32, 2 * s + 32, 2 * s, s),
        (0, s + 32, s, 2 * s),
        (s + 32, s + 32, s - 32, s - 32),
    ]
    pieces = [instance(w, h, uid=i + 1) for i, (_, _, w, h) in enumerate(raw)]
    placements = [
        Placement(p, 0, x + 100, y + 100, w, h) for p, (x, y, w, h) in zip(pieces, raw, strict=True)
    ]
    saw = make(placements)
    assert "NOT_GUILLOTINE" in codes(saw, pieces)
    cnc = make(placements, replace(PARAMS, cut_mode=CutMode.CNC))
    assert codes(cnc, pieces) == set()
