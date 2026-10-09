"""Piezas preparadas para versiones futuras (sin UI): generador de despiece y costos."""

import inspect

import pytest

from database.database import Database
from models.costos import CostBreakdown, MaterialCost
from models.parametros import CuttingParameters
from models.pieza import PieceCategory, expand_pieces
from models.placa import PlateFormat, PlateGrain
from models.proyecto import Furniture, FurnitureDimensions, Project
from models.resultado import OptimizationResult
from models.validation import validate_piece
from optimization.optimizer import OptimizationRequest, Optimizer
from optimization.verification import verify_result
from services.cost_service import CostService
from services.furniture_generator import GENERATORS, DeskGenerator, get_generator
from utils.units import mm_to_internal

T = mm_to_internal(18)


def desk(width=1200, height=750, depth=600, **params) -> Furniture:
    dims = FurnitureDimensions(*(mm_to_internal(v) for v in (width, height, depth)))
    return Furniture("Escritorio", dimensions=dims, generator_id="desk", generator_params=params)


class TestDeskGenerator:
    def test_is_experimental_and_not_registered(self):
        assert "experimental" in DeskGenerator.name.lower()
        assert DeskGenerator.id not in GENERATORS
        with pytest.raises(KeyError):
            get_generator(DeskGenerator.id)

    def test_breakdown(self):
        pieces = {p.name: p for p in DeskGenerator().generate(desk(), T)}
        assert set(pieces) == {"Tapa", "Lateral", "Faldón"}
        top, side, modesty = pieces["Tapa"], pieces["Lateral"], pieces["Faldón"]
        assert (top.width_mm, top.height_mm, top.quantity) == (1200, 600, 1)
        assert (side.width_mm, side.height_mm, side.quantity) == (600, 732, 2)
        assert (modesty.width_mm, modesty.height_mm) == (1164, 300)
        assert side.category is PieceCategory.LATERAL
        assert all(p.thickness == T for p in pieces.values())

    def test_modesty_height_parameter(self):
        pieces = DeskGenerator().generate(desk(modesty_height_mm=250), T)
        assert next(p for p in pieces if p.name == "Faldón").height_mm == 250

    @pytest.mark.parametrize("furniture", [Furniture("Sin medidas"), desk(width=30)])
    def test_rejects_missing_or_tiny_dimensions(self, furniture):
        with pytest.raises(ValueError):
            DeskGenerator().generate(furniture, T)

    def test_pipeline_dimensions_to_optimizer(self):
        """Dimensiones → Despiece → Piezas → Optimizador, con una placa con veta."""
        plate = PlateFormat.from_mm("Roble", 1830, 2820, 18, grain=PlateGrain.ALONG_HEIGHT)
        params = CuttingParameters()
        specs = DeskGenerator().generate(desk(), plate.thickness)
        assert all(validate_piece(s, plate, params) == [] for s in specs)
        pieces = expand_pieces(specs)
        result = Optimizer(OptimizationRequest(pieces, plate, params), time_budget_s=2).run()
        assert not result.unplaced and result.pieces_count == 4
        assert verify_result(result, pieces, plate.grain) == []


class TestCostService:
    def test_signature_is_ready(self):
        signature = inspect.signature(CostService.compute)
        assert list(signature.parameters) == ["self", "project", "result", "material_costs"]
        assert signature.parameters["material_costs"].default is None
        assert signature.return_annotation in (CostBreakdown, "CostBreakdown")

    def test_not_implemented_yet(self):
        with pytest.raises(NotImplementedError):
            CostService().compute(
                Project("X"),
                OptimizationResult(CuttingParameters()),
                {1: MaterialCost(1, 100_000, 20_000)},
            )

    def test_cost_tables_exist(self):
        db = Database(":memory:")
        db.migrate()
        rows = db.query("SELECT name FROM sqlite_master WHERE type = 'table'")
        assert {"hardware_items", "furniture_hardware"} <= {r["name"] for r in rows}
        db.close()
