"""Retazos: clasificación, fusión, cuadre de áreas y paso a stock."""

from dataclasses import replace

import pytest

from database.seed import seed
from models.parametros import CuttingParameters
from models.resultado import SheetSource
from models.retazo import OffcutStatus
from optimization.cutting import CuttingPlanner, plan_result
from optimization.guillotine import decompose
from optimization.offcuts import classify, merge_offcuts
from services.inventory_service import InventoryService
from services.optimization_service import OptimizationService
from services.project_service import ProjectService
from tests.helpers import assert_plan_reconstructs, params_mm, piece, plate_mm, run
from tests.test_cutting_plan import sheet_with
from utils.geometry import Rect
from utils.units import mm_to_internal


def mm_rect(w, h) -> Rect:
    return Rect(0, 0, mm_to_internal(w), mm_to_internal(h))


# ---------------------------------------------------------------- clasificación


@pytest.mark.parametrize(
    ("w", "h", "status"),
    [
        (600, 400, OffcutStatus.REUSABLE),
        (100, 20, OffcutStatus.WASTE),
        (150, 340, OffcutStatus.REUSABLE),  # justo en el mínimo de ancho y 0,051 m²
        ("149.9", 2000, OffcutStatus.WASTE),  # demasiado estrecho aunque sea largo
        (200, 200, OffcutStatus.WASTE),  # 0,04 m² < 0,05 m²
        (2000, 150, OffcutStatus.REUSABLE),  # acostado también vale
    ],
)
def test_classification_by_default_minimums(w, h, status):
    assert classify(mm_rect(w, h), CuttingParameters()) is status


def test_classification_accepts_minimums_in_either_orientation():
    params = replace(
        CuttingParameters(),
        min_offcut_width=mm_to_internal(300),
        min_offcut_height=mm_to_internal(100),
        min_offcut_area=0,
    )
    assert classify(mm_rect(300, 100), params) is OffcutStatus.REUSABLE
    assert classify(mm_rect(100, 300), params) is OffcutStatus.REUSABLE
    assert classify(mm_rect(250, 250), params) is OffcutStatus.WASTE


# ---------------------------------------------------------------- fusión

K = 32  # 3,2 mm
# Columna de 3 piezas a la izquierda y una arriba a la derecha. El descomponedor corta
# primero en 3 tiras horizontales, y los sobrantes de la derecha de las tiras 2 y 3
# quedan separados por un corte que sobra.
COLUMN = [
    ("P1", 0, 0, 6000, 3000),
    ("P2", 0, 3032, 6000, 3000),
    ("P3", 0, 6064, 6000, 3936),
    ("P4", 15000, 0, 5000, 3000),
]


def test_adjacent_offcuts_are_merged_with_one_cut_less():
    region = Rect(0, 0, 20000, 10000)
    pieces = [Rect(x, y, w, h) for _, x, y, w, h in COLUMN]
    before = decompose(pieces, region, K)
    merged = merge_offcuts(pieces, before.leftovers, region, K)
    assert len(merged) == len(before.leftovers) - 1
    assert Rect(6032, 3032, 13968, 6968) in merged
    after = decompose([*pieces, *merged], region, K)
    assert after.cut_count == before.cut_count - 1


def test_planner_reports_the_merged_offcut():
    params = params_mm("3.2", "0")
    planned = CuttingPlanner(params).plan_sheet(sheet_with(20000, 10000, COLUMN))
    reusable = [o for o in planned.offcuts if o.status is OffcutStatus.REUSABLE]
    assert (reusable[0].x, reusable[0].y, reusable[0].width, reusable[0].height) == (
        6032,
        3032,
        13968,
        6968,
    )
    assert reusable[0].label == "R1.1"  # el mayor primero
    assert planned.cut_plan.cut_count == 5
    assert_plan_reconstructs(planned, params)


def test_merge_never_breaks_guillotine():
    region = Rect(0, 0, 20000, 20000)
    pieces = [Rect(0, 0, 5000, 5000), Rect(5032, 5032, 5000, 5000)]
    d = decompose(pieces, region, K)
    merged = merge_offcuts(pieces, d.leftovers, region, K)
    assert decompose([*pieces, *merged], region, K) is not None
    assert all(not m.intersects(p) for m in merged for p in pieces)


# ---------------------------------------------------------------- cuadre de áreas


def test_areas_add_up_exactly():
    params = params_mm("3.2", "10")
    specs = [
        piece("Lateral", 2, 600, 720),
        piece("Estante", 5, 564, 300),
        piece("Tapa", 1, 600, 900),
    ]
    result = plan_result(run(specs, plate_mm(1830, 2820), params))
    for sheet in result.sheets:
        reusable = sum(o.area for o in sheet.offcuts if o.status is OffcutStatus.REUSABLE)
        waste = sum(o.area for o in sheet.offcuts if o.status is OffcutStatus.WASTE)
        assert sheet.used_area + sheet.kerf_area + reusable + waste == sheet.total_area
        assert sheet.reusable_offcut_area == reusable
        assert sheet.unusable_waste_area == sheet.kerf_area + waste
        refilado = [o for o in sheet.offcuts if o.notes == "Refilado"]
        assert len(refilado) == 4 and all(o.status is OffcutStatus.WASTE for o in refilado)


def test_offcuts_carry_plate_material_and_position():
    params = params_mm()
    result = plan_result(
        run([piece("A", 1, 600, 600)], plate_mm(1830, 2820), params), material_id=7
    )
    off = result.sheets[0].offcuts[0]
    assert off.status is OffcutStatus.REUSABLE and off.material_id == 7
    assert off.sheet_index == 0 and off.x is not None and off.thickness == 180


# ---------------------------------------------------------------- paso a stock


def optimized_demo(db):
    project = ProjectService(db).open(seed(db).demo_project_id)
    return project, OptimizationService(db).optimize(project).result


def test_save_offcuts_to_stock_and_mark_result(db):
    project, result = optimized_demo(db)
    inventory = InventoryService(db)
    reusable = [o for s in result.sheets for o in s.offcuts if o.status is OffcutStatus.REUSABLE]
    stored = inventory.save_offcuts(result.id)
    assert len(stored) == len(reusable) > 0
    assert all(
        o.status is OffcutStatus.IN_STOCK and o.source_result_id == result.id for o in stored
    )
    assert {(o.width, o.height) for o in inventory.available_offcuts()} == {
        (o.width, o.height) for o in reusable
    }
    # el resultado guardado recuerda qué retazos pasaron a stock: no se duplican
    again = OptimizationService(db).latest_result(project.id)
    assert {o.id for s in again.sheets for o in s.offcuts if o.id} == {o.id for o in stored}
    assert again.sheets[0].reusable_offcut_area == result.sheets[0].reusable_offcut_area
    assert inventory.save_offcuts(result.id) == []
    assert len(inventory.available_offcuts()) == len(stored)


def test_save_selected_offcut_and_reject_waste(db):
    _, result = optimized_demo(db)
    inventory = InventoryService(db)
    stored = inventory.save_offcuts(result.id, ["R1.1"])
    assert len(stored) == 1 and "R1.1" in stored[0].notes
    with pytest.raises(ValueError, match="R9.9"):
        inventory.save_offcuts(result.id, ["R9.9"])
    assert len(inventory.available_offcuts()) == 1


def test_stored_offcut_is_used_as_bin_in_next_optimization(db):
    project, result = optimized_demo(db)
    InventoryService(db).save_offcuts(result.id, ["R1.1"])
    project = replace(project, params=replace(project.params, use_offcuts_first=True))
    second = OptimizationService(db).optimize(project, save=False).result
    assert second.sheets[0].source is SheetSource.OFFCUT
    assert second.sheets[0].edge_margin == 0  # retazo ya escuadrado: sin refilado
    assert_plan_reconstructs(second.sheets[0], second.params)
