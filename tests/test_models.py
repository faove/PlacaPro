import json
from decimal import Decimal

import pytest

from models.costos import CostBreakdown, HardwareItem, HardwareLine, LaborCost
from models.parametros import CutMode, CuttingParameters, OptimizationLevel
from models.pieza import GrainDirection, PieceCategory, PieceSpec, expand_pieces
from models.placa import PlateFormat
from models.plan_corte import Cut, CutOrientation, CutPlan
from models.proyecto import Furniture, Project
from models.resultado import (
    OptimizationResult,
    Placement,
    SheetLayout,
    SheetSource,
    UnplacedPiece,
)
from models.retazo import Offcut, OffcutStatus
from utils.geometry import Rect


def lateral(quantity=2):
    return PieceSpec.from_mm("Lateral", quantity, 400, 600, 18, category=PieceCategory.LATERAL)


class TestPlateFormat:
    def test_from_mm_and_labels(self):
        plate = PlateFormat.from_mm("Melamina blanca 18 mm", 1830, 2820, 18)
        assert (plate.width, plate.height, plate.thickness) == (18300, 28200, 180)
        assert plate.width_mm == Decimal(1830)
        assert plate.dimensions_label == "1830 × 2820 × 18 mm"
        assert plate.area == 18300 * 28200

    def test_usable_rect(self):
        plate = PlateFormat.from_mm("P", 1830, 2820, 18)
        assert plate.usable_rect(100) == Rect(100, 100, 18100, 28000)

    def test_rejects_float_dimensions(self):
        with pytest.raises(TypeError):
            PlateFormat("P", 1830.0, 2820, 18)  # type: ignore[arg-type]


class TestPieceExpansion:
    def test_quantity_becomes_numbered_instances(self):
        instances = lateral(2).expand()
        assert [i.label for i in instances] == ["Lateral 1", "Lateral 2"]
        assert [i.index for i in instances] == [1, 2]
        assert all(i.width == 4000 and i.height == 6000 for i in instances)

    def test_single_piece_has_no_number(self):
        assert PieceSpec.from_mm("Tapa", 1, 564, 400, 18).expand()[0].label == "Tapa"

    def test_zero_quantity_expands_to_nothing(self):
        assert PieceSpec.from_mm("X", 0, 100, 100, 18).expand() == []

    def test_expand_pieces_gives_unique_consecutive_uids(self):
        specs = [lateral(2), PieceSpec.from_mm("Tapa", 1, 564, 400, 18), lateral(3)]
        instances = expand_pieces(specs)
        assert [i.uid for i in instances] == [1, 2, 3, 4, 5, 6]
        assert len({i.uid for i in instances}) == 6

    def test_areas(self):
        spec = lateral(2)
        assert spec.area == 4000 * 6000
        assert spec.total_area == 2 * 4000 * 6000

    def test_dict_round_trip(self):
        spec = PieceSpec.from_mm(
            "Puerta",
            2,
            "282.5",
            600,
            18,
            category=PieceCategory.PUERTA,
            grain=GrainDirection.VERTICAL,
            can_rotate=False,
            fixed_orientation=True,
            notes="frente",
            id=7,
        )
        assert PieceSpec.from_dict(json.loads(json.dumps(spec.to_dict()))) == spec


class TestParameters:
    def test_defaults_in_internal_units(self):
        p = CuttingParameters()
        assert (p.kerf, p.edge_margin, p.extra_spacing) == (32, 100, 0)
        assert p.min_offcut_area == 5_000_000  # 0,05 m² en dmm²
        assert p.cut_gap == 32

    def test_round_trip_and_tolerance(self):
        p = CuttingParameters(kerf=40, level=OptimizationLevel.MAX, cut_mode=CutMode.CNC)
        data = json.loads(json.dumps(p.to_dict()))
        assert CuttingParameters.from_dict(data) == p
        assert CuttingParameters.from_dict({"kerf": 30, "unknown": 1}).kerf == 30

    def test_rejects_float(self):
        with pytest.raises(TypeError):
            CuttingParameters(kerf=3.2)  # type: ignore[arg-type]


class TestProject:
    def test_duplicate_is_deep_and_without_ids(self):
        spec = PieceSpec.from_mm("Lateral", 2, 400, 600, 18, id=5)
        project = Project("Mesita", furniture=[Furniture("Mesita", [spec], id=3)], id=9)
        clone = project.duplicate("Mesita copia")
        assert clone.name == "Mesita copia" and clone.id is None
        assert clone.furniture[0].id is None and clone.furniture[0].pieces[0].id is None
        clone.furniture[0].pieces.append(spec)
        assert len(project.furniture[0].pieces) == 1  # el original no cambia

    def test_instances_across_furniture(self):
        project = Project(
            "P",
            furniture=[Furniture("A", [lateral(2)]), Furniture("B", [lateral(3)])],
        )
        assert project.total_piece_count == 5
        assert len(project.piece_instances()) == 5


def make_result():
    inst = lateral(2).expand()
    placements = (
        Placement(inst[0], 0, 100, 100, 4000, 6000),
        Placement(inst[1], 0, 4132, 100, 6000, 4000, rotated=True),
    )
    offcut = Offcut(6000, 4000, 180, OffcutStatus.REUSABLE, x=100, y=6132, sheet_index=0)
    plan = CutPlan(0, (Cut(1, 1, CutOrientation.HORIZONTAL, 6100, 0, 18300, 6000, False, ("A",)),))
    sheet = SheetLayout(0, 18300, 28200, 180, SheetSource.NEW, 1, None, placements, (offcut,), plan)
    unplaced = (
        UnplacedPiece(PieceSpec.from_mm("Gigante", 1, 3000, 3000, 18).expand()[0], "no cabe"),
    )
    return OptimizationResult(
        CuttingParameters(), (sheet,), unplaced, "guillotine-baf", (1, 2, 3), 1, 12, project_id=4
    )


class TestResult:
    def test_metrics(self):
        result = make_result()
        sheet = result.sheets[0]
        used = 2 * 4000 * 6000
        assert sheet.used_area == used
        assert sheet.waste_area == 18300 * 28200 - used
        assert sheet.used_area + sheet.waste_area == sheet.total_area
        assert sheet.reusable_offcut_area == 24_000_000
        assert sheet.unusable_waste_area == sheet.waste_area - 24_000_000
        assert result.sheets_count == 1 and result.pieces_count == 2
        assert result.utilization == pytest.approx(used / (18300 * 28200))
        assert not result.is_complete

    def test_json_round_trip(self):
        result = make_result()
        restored = OptimizationResult.from_dict(json.loads(json.dumps(result.to_dict())))
        assert restored == result
        assert restored.sheets[0].cut_plan.total_cut_length == 18300


def test_cost_breakdown_margin():
    hinge = HardwareItem("Bisagra", 250)
    labor = LaborCost(Decimal("2.5"), 1000)
    assert HardwareLine(hinge, 4).total_cents == 1000
    assert labor.total_cents == 2500
    costs = CostBreakdown(
        plates_cents=6500, hardware_cents=1000, labor_cents=2500, sale_price_cents=20000
    )
    assert costs.total_cents == 10000
    assert costs.margin_pct == Decimal(50)
    assert CostBreakdown().margin_pct == 0
