"""Propiedades que deben cumplirse para CUALQUIER entrada válida (Hypothesis)."""

from dataclasses import replace
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from models.parametros import CutMode, CuttingParameters, OptimizationLevel
from models.pieza import GrainDirection, PieceSpec, expand_pieces
from models.placa import PlateFormat, PlateGrain
from optimization.cutting import plan_result
from optimization.guillotine import decompose
from optimization.optimizer import OptimizationRequest, Optimizer
from optimization.verification import verify_result
from tests.helpers import assert_plan_reconstructs
from utils.geometry import Rect

PLATES = [(18300, 28200), (24400, 12200), (27500, 18300), (6000, 4000)]

pieces_st = st.lists(
    st.builds(
        lambda q, w, h, rot, grain, fixed: PieceSpec(
            "P", q, w, h, 180, can_rotate=rot, grain=grain, fixed_orientation=fixed
        ),
        st.integers(1, 3),
        st.integers(300, 14000),  # 30 mm .. 1400 mm, con décimas
        st.integers(300, 14000),
        st.booleans(),
        st.sampled_from(list(GrainDirection)),
        st.booleans(),
    ),
    min_size=1,
    max_size=10,
)

params_st = st.builds(
    lambda kerf, margin, spacing, rot, mode: CuttingParameters(
        kerf=kerf,
        edge_margin=margin,
        extra_spacing=spacing,
        allow_rotation=rot,
        level=OptimizationLevel.FAST,
        cut_mode=mode,
    ),
    st.integers(0, 50),
    st.integers(0, 200),
    st.integers(0, 20),
    st.booleans(),
    st.sampled_from(list(CutMode)),
)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    specs=pieces_st,
    params=params_st,
    plate_dims=st.sampled_from(PLATES),
    grain=st.sampled_from(list(PlateGrain)),
)
def test_invariants_hold_for_any_input(specs, params, plate_dims, grain):
    plate = PlateFormat("P", *plate_dims, 180, grain=grain)
    pieces = expand_pieces(specs)
    result = Optimizer(OptimizationRequest(pieces, plate, params)).run()

    # 1-5 y conservación: sin solapes, kerf, márgenes, medidas exactas, veta, sin perder piezas
    assert verify_result(result, pieces, plate.grain) == []
    # 6. nunca menos placas que la cota inferior
    assert result.sheets_count >= result.lower_bound
    # 8. contabilidad exacta de áreas
    for sheet in result.sheets:
        assert sheet.used_area + sheet.waste_area == sheet.total_area
        assert sheet.placements
    assert result.used_area == sum(p.piece.area for p in result.placements)
    # 7. en escuadradora todo es guillotinable y los sobrantes no pisan piezas
    if params.cut_mode is CutMode.PANEL_SAW:
        for sheet in result.sheets:
            rects = [p.rect for p in sheet.placements]
            d = decompose(rects, Rect(0, 0, sheet.width, sheet.height), params.kerf)
            assert d is not None
            for left in d.leftovers:
                assert all(not left.intersects(r) for r in rects)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    specs=pieces_st,
    params=params_st,
    plate_dims=st.sampled_from(PLATES),
    grain=st.sampled_from(list(PlateGrain)),
)
def test_panel_saw_plan_reconstructs_every_layout(specs, params, plate_dims, grain):
    """9. En escuadradora, la secuencia de cortes reconstruye exactamente las piezas, con el
    kerf restado en cada corte, y piezas + kerf + retazos + desperdicio = área de la placa."""
    params = replace(params, cut_mode=CutMode.PANEL_SAW)
    plate = PlateFormat("P", *plate_dims, 180, grain=grain)
    result = plan_result(Optimizer(OptimizationRequest(expand_pieces(specs), plate, params)).run())
    for sheet in result.sheets:
        assert sheet.cut_plan is not None and sheet.cut_plan.mode is CutMode.PANEL_SAW
        assert_plan_reconstructs(sheet, params)


@settings(max_examples=25, deadline=None)
@given(specs=pieces_st, plate_dims=st.sampled_from(PLATES))
def test_balanced_never_worse_than_fast(specs, plate_dims):
    plate = PlateFormat("P", *plate_dims, 180)
    pieces = expand_pieces(specs)
    fast = Optimizer(
        OptimizationRequest(pieces, plate, CuttingParameters(level=OptimizationLevel.FAST))
    ).run()
    balanced = Optimizer(
        OptimizationRequest(pieces, plate, CuttingParameters(level=OptimizationLevel.BALANCED))
    ).run()
    assert balanced.score <= fast.score


def test_decimal_dimensions_are_exact():
    """Piezas con décimas de mm: las coordenadas resultantes son exactas (enteros dmm)."""
    spec = PieceSpec.from_mm("P", 4, Decimal("450.5"), Decimal("300.3"), 18)
    plate = PlateFormat.from_mm("P", 1830, 2820, 18)
    result = Optimizer(OptimizationRequest(spec.expand(), plate, CuttingParameters())).run()
    for p in result.placements:
        assert {p.width, p.height} == {4505, 3003}
        assert isinstance(p.x, int) and isinstance(p.y, int)
