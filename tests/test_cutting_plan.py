"""Plan de corte físico: secuencia de escuadradora, refilado, tope, modo CNC."""

from dataclasses import replace

import pytest

from database.seed import seed
from models.parametros import CutMode
from models.pieza import PieceSpec, expand_pieces
from models.plan_corte import CutOrientation, CutPlan
from models.resultado import OptimizationResult, Placement, SheetLayout
from optimization.cutting import CuttingPlanner, NodeKind, format_plan, plan_result
from optimization.guillotine import is_guillotine
from optimization.scoring import Score
from services.optimization_service import OptimizationService
from services.project_service import ProjectService
from tests.helpers import assert_plan_reconstructs, params_mm, piece, plate_mm, run
from utils.geometry import Rect

H, V = CutOrientation.HORIZONTAL, CutOrientation.VERTICAL


def sheet_with(width: int, height: int, rects: list[tuple[str, int, int, int, int]], margin=0):
    """Placa con piezas colocadas a mano (coordenadas en dmm)."""
    specs = [PieceSpec(name, 1, w, h, 180) for name, _, _, w, h in rects]
    placements = tuple(
        Placement(inst, 0, x, y, w, h)
        for inst, (_, x, y, w, h) in zip(expand_pieces(specs), rects, strict=True)
    )
    return SheetLayout(0, width, height, 180, placements=placements, edge_margin=margin)


# ---------------------------------------------------------------- casos del sprint


def test_two_pieces_in_a_row_trim_strip_and_separation():
    """Refilado (4) + 1 corte de tira + 1 corte de separación, con las medidas de tope."""
    params = params_mm("3.2", "10")
    # ancho útil = 400 + 3,2 + 400 → la fila llena la placa a lo ancho
    sheet = sheet_with(
        8232, 20000, [("A", 100, 100, 4000, 6000), ("B", 4132, 100, 4000, 6000)], margin=100
    )
    planned = CuttingPlanner(params).plan_sheet(sheet)
    cuts = planned.cut_plan.cuts
    assert [(c.level, c.is_trim) for c in cuts] == [(0, True)] * 4 + [(1, False), (2, False)]

    strip, separation = cuts[4], cuts[5]
    assert (strip.orientation, strip.position, strip.length) == (H, 6100, 8032)
    assert strip.fence_distance == 6000  # ancho de la tira
    assert (separation.orientation, separation.position, separation.length) == (V, 4100, 6000)
    assert separation.fence_distance == 4000
    assert separation.resulting == ("A (400 × 600)", "B (400 × 600)")
    assert_plan_reconstructs(planned, params)


def test_edge_trim_positions_and_fence():
    params = params_mm("3.2", "10")
    sheet = sheet_with(18300, 28200, [("A", 100, 100, 5000, 5000)], margin=100)
    trims = [c for c in CuttingPlanner(params).plan(sheet).cuts if c.is_trim]
    # izquierda, derecha, arriba, abajo; el kerf cae dentro del margen
    assert [(c.orientation, c.position) for c in trims] == [
        (V, 68),
        (V, 18200),
        (H, 68),
        (H, 28100),
    ]
    # tras refilar un borde, el tope del opuesto es la medida útil
    assert [c.fence_distance for c in trims] == [68, 18100, 68, 28000]
    assert [c.length for c in trims] == [28200, 28200, 18100, 18100]


def test_margin_narrower_than_kerf_clips_the_trim():
    params = params_mm("3.2", "2")
    sheet = sheet_with(10000, 10000, [("A", 20, 20, 5000, 5000)], margin=20)
    planned = CuttingPlanner(params).plan_sheet(sheet)
    trims = [c for c in planned.cut_plan.cuts if c.is_trim]
    assert [c.kerf for c in trims] == [20, 20, 20, 20]
    assert not [o for o in planned.offcuts if o.notes == "Refilado"]
    assert_plan_reconstructs(planned, params)


def test_no_margin_no_trim_cuts():
    params = params_mm("3.2", "0")
    sheet = sheet_with(10000, 10000, [("A", 0, 0, 5000, 10000)])
    planned = CuttingPlanner(params).plan_sheet(sheet)
    assert [c.is_trim for c in planned.cut_plan.cuts] == [False]
    assert_plan_reconstructs(planned, params)


def test_piece_filling_the_plate_needs_no_cut():
    params = params_mm("3.2", "0")
    planned = CuttingPlanner(params).plan_sheet(sheet_with(5000, 5000, [("A", 0, 0, 5000, 5000)]))
    assert planned.cut_plan.cuts == () and planned.offcuts == ()


PINWHEEL = [  # molinete: 5 piezas sin ninguna línea de corte de borde a borde
    ("N", 0, 0, 20000, 10000),
    ("E", 20000, 0, 10000, 20000),
    ("S", 10000, 20000, 20000, 10000),
    ("O", 0, 10000, 10000, 20000),
    ("C", 10000, 10000, 10000, 10000),
]


def test_pinwheel_is_detected_as_not_guillotine():
    rects = [Rect(x, y, w, h) for _, x, y, w, h in PINWHEEL]
    assert not is_guillotine(rects, Rect(0, 0, 30000, 30000), 0)
    with pytest.raises(ValueError, match="guillotina"):
        CuttingPlanner(params_mm("0", "0")).plan(sheet_with(30000, 30000, PINWHEEL))


def test_pinwheel_in_cnc_mode_gives_contours_and_outer_offcut():
    params = params_mm("0", "0", cut_mode=CutMode.CNC)
    sheet = sheet_with(50000, 30000, PINWHEEL)
    built = CuttingPlanner(params).build(sheet)
    plan = built.cut_plan
    assert plan.mode is CutMode.CNC and plan.cuts == ()
    assert [c.label for c in plan.contours] == ["N", "E", "S", "O", "C"]
    assert len(built.tree.leaves(NodeKind.BLOCK)) == 1
    # la parte que sí se puede separar (a la derecha del molinete) es un retazo
    assert [(o.x, o.y, o.width, o.height) for o in built.offcuts] == [(30000, 0, 20000, 30000)]
    assert "CNC" in format_plan(replace(sheet, cut_plan=plan))


def test_guillotine_layout_in_cnc_mode_still_gets_saw_plan():
    params = params_mm("3.2", "10", cut_mode=CutMode.CNC)
    sheet = sheet_with(10000, 10000, [("A", 100, 100, 3000, 3000)], margin=100)
    assert CuttingPlanner(params).plan(sheet).mode is CutMode.PANEL_SAW


def test_cuts_released_cover_every_piece_once():
    params = params_mm()
    specs = [
        piece("Lateral", 4, 560, 720),
        piece("Estante", 6, 764, 300),
        piece("Fondo", 2, 800, 720),
    ]
    result = plan_result(run(specs, plate_mm(1830, 2820), params))
    for sheet in result.sheets:
        released = [text for c in sheet.cut_plan.cuts for text in c.resulting]
        for p in sheet.placements:
            assert sum(t.startswith(f"{p.piece.label} (") for t in released) == 1
        assert_plan_reconstructs(sheet, params)


def test_plan_metrics():
    params = params_mm("3.2", "10")
    sheet = sheet_with(
        8232, 20000, [("A", 100, 100, 4000, 6000), ("B", 4132, 100, 4000, 6000)], margin=100
    )
    plan = CuttingPlanner(params).plan(sheet)
    assert plan.cut_count == 6
    assert plan.cuts_by_level == {0: 4, 1: 1, 2: 1}
    assert plan.total_cut_length == sum(c.length for c in plan.cuts)
    assert plan.kerf_area == sum(c.kerf * c.length for c in plan.cuts)


def test_plan_round_trips_through_dict():
    params = params_mm()
    result = plan_result(run([piece("A", 3, 500, 400)], plate_mm(1830, 2820), params))
    sheet = result.sheets[0]
    assert CutPlan.from_dict(sheet.cut_plan.to_dict()) == sheet.cut_plan
    assert OptimizationResult.from_dict(result.to_dict()) == result


# ---------------------------------------------------------------- demo «Mesita de noche»


def test_demo_produces_readable_sequence_and_is_persisted(db):
    project = ProjectService(db).open(seed(db).demo_project_id)
    service = OptimizationService(db)
    result = service.optimize(project).result
    sheet = result.sheets[0]
    assert sheet.cut_plan is not None and sheet.cut_plan.cut_count > 4
    assert_plan_reconstructs(sheet, result.params)

    text = format_plan(sheet, "Melamina 18 mm")
    lines = text.splitlines()
    assert lines[0] == "PLACA 1 — Melamina 18 mm (1830 × 2820)"
    assert lines[1].startswith("CORTE 1 ") and "[refilado]" in lines[1]
    assert "longitud   2820 mm" in lines[1]
    for p in sheet.placements:
        assert p.piece.label in text

    # los retazos se clasifican y quedan guardados con el resultado
    assert sheet.reusable_offcut_area > 0
    assert sheet.used_area + sheet.kerf_area + sum(o.area for o in sheet.offcuts) == (
        sheet.total_area
    )
    assert service.latest_result(project.id).sheets[0].cut_plan == sheet.cut_plan


def test_scoring_breaks_ties_by_cut_count():
    """A igualdad de placas y sobrantes, gana la solución con menos cortes."""
    fewer = Score(0, 1, 0, 10**6, -(10**5), cut_count=3, cut_length=10**9)
    more = Score(0, 1, 0, 10**6, -(10**5), cut_count=4, cut_length=0)
    assert fewer < more
    # el optimizador cuenta los cortes con el mismo árbol que el plan (sin refilado)
    result = run([piece("A", 4, 500, 500)], plate_mm(1000, 1000), params_mm("0", "0"))
    assert result.score[-2] == plan_result(result).sheets[0].cut_plan.cut_count == 3
