import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from database.repositories import InsufficientStockError
from database.seed import DEMO_PROJECT_NAME, seed
from models.pieza import PieceSpec
from models.placa import PlateFormat
from models.retazo import Offcut, OffcutStatus
from models.validation import IssueCode, ValidationFailed
from services.cost_service import CostService
from services.furniture_generator import GENERATORS, ManualGenerator, get_generator
from services.inventory_service import InventoryService
from services.plate_service import PlateService
from services.project_service import ProjectService
from utils.units import mm_to_internal


class TestSeed:
    def test_seed_creates_formats_materials_and_demo(self, db):
        result = seed(db)
        assert result.seeded and result.demo_project_id is not None
        plates = PlateService(db).list_formats()
        sizes = {(p.width_mm, p.height_mm) for p in plates}
        assert sizes == {(1830, 2820), (2440, 1220), (2750, 1830), (2800, 2070), (3000, 2100)}
        assert {m.name for m in PlateService(db).list_materials()} >= {
            "Melamina",
            "MDF",
            "Fenólico",
        }

        demo = ProjectService(db).open(result.demo_project_id)
        assert demo.name == DEMO_PROJECT_NAME
        plate = PlateService(db).get_format(demo.plate_format_id)
        assert plate.dimensions_label == "1830 × 2820 × 18 mm"
        dims = sorted((p.quantity, p.width_mm, p.height_mm) for p in demo.all_piece_specs())
        assert dims == sorted(
            [(2, 400, 600), (1, 564, 400), (1, 564, 600), (2, 282, 600), (1, 564, 100)]
        )
        assert ProjectService(db).validate(demo).issues == []

    def test_seed_is_idempotent_and_respects_deletions(self, db):
        first = seed(db)
        second = seed(db)
        assert not second.seeded and second.demo_project_id == first.demo_project_id
        assert len(ProjectService(db).list_projects()) == 1
        assert len(PlateService(db).list_formats()) == 5

        ProjectService(db).delete(first.demo_project_id)
        third = seed(db)
        assert third.demo_project_id is None
        assert ProjectService(db).list_projects() == []


class TestProjectService:
    def test_full_flow(self, db):
        seed(db)
        service = ProjectService(db)
        plate = PlateService(db).list_formats()[0]

        project = service.new_project("Mueble bajo", plate.id)
        assert project.id is None and len(project.furniture) == 1
        project.furniture[0].pieces.append(PieceSpec.from_mm("Lateral", 2, 700, 500, 18))
        saved = service.save(project)
        assert saved.id is not None

        opened = service.open(saved.id)
        assert opened == saved

        copy = service.save_as(opened, "Mueble bajo v2")
        assert copy.id != saved.id and service.open(saved.id).name == "Mueble bajo"

        dup = service.duplicate(saved.id)
        assert dup.name == "Mueble bajo (copia)"

        service.delete(saved.id)
        names = {s.name for s in service.list_projects()}
        assert "Mueble bajo" not in names and {"Mueble bajo v2", "Mueble bajo (copia)"} <= names

    def test_save_requires_name(self, db):
        service = ProjectService(db)
        with pytest.raises(ValidationFailed) as exc:
            service.save(service.new_project("   "))
        assert exc.value.report.codes() == {IssueCode.EMPTY_NAME}

    def test_validate_reports_missing_plate(self, db):
        service = ProjectService(db)
        project = service.new_project("Sin placa", plate_format_id=12345)
        report = service.validate(project)
        assert IssueCode.NO_PLATE_SELECTED in report.codes()


class TestPlateService:
    def test_save_validates(self, db):
        service = PlateService(db)
        with pytest.raises(ValidationFailed):
            service.save_format(PlateFormat("", 0, 0, 0))
        saved = service.save_format(PlateFormat.from_mm("Fenólico 18", 2440, 1220, 18))
        assert service.get_format(saved.id) == saved
        service.delete_format(saved.id)
        assert service.list_formats() == []


class TestInventoryService:
    def test_plates(self, db):
        plate = PlateService(db).save_format(PlateFormat.from_mm("P", 1830, 2820, 18))
        inventory = InventoryService(db)
        inventory.set_available_plates(plate.id, 5)
        assert inventory.available_plates(plate.id) == 5
        assert inventory.consume_plates(plate.id, 2) == 3
        with pytest.raises(InsufficientStockError):
            inventory.consume_plates(plate.id, 4)

    def test_offcuts(self, db):
        inventory = InventoryService(db)
        result_offcut = Offcut(6000, 4000, 180, OffcutStatus.REUSABLE, x=100, y=200, sheet_index=0)
        stored = inventory.store_offcut(result_offcut)
        assert stored.status is OffcutStatus.IN_STOCK and stored.x is None
        assert inventory.available_offcuts(thickness=180) == [stored]
        inventory.mark_offcut_consumed(stored.id)
        assert inventory.available_offcuts() == []


def test_manual_generator_returns_pieces():
    from models.proyecto import Furniture

    pieces = [PieceSpec.from_mm("Lateral", 2, 700, 500, 18)]
    generator = get_generator("manual")
    assert isinstance(generator, ManualGenerator) and "manual" in GENERATORS
    assert generator.generate(Furniture("M", pieces), mm_to_internal(18)) == pieces
    with pytest.raises(KeyError):
        get_generator("escritorio")


def test_cost_service_is_pending(db):
    from models.parametros import CuttingParameters
    from models.resultado import OptimizationResult

    service = ProjectService(db)
    with pytest.raises(NotImplementedError):
        CostService().compute(service.new_project("X"), OptimizationResult(CuttingParameters()))


def test_core_layers_do_not_import_qt():
    """Dominio, persistencia, servicios y optimización deben funcionar sin PySide6."""
    root = Path(__file__).resolve().parents[1]
    modules = [
        ".".join(p.relative_to(root).with_suffix("").parts)
        for package in ("models", "database", "services", "optimization", "utils")
        for p in (root / package).glob("*.py")
    ]
    code = (
        "import sys\n"
        + "".join(f"import {m}\n" for m in modules)
        + "assert 'PySide6' not in sys.modules, 'PySide6 importado'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_piece_dimensions_survive_round_trip_exactly(db):
    seed(db)
    service = ProjectService(db)
    project = service.new_project("Precisión", PlateService(db).list_formats()[0].id)
    spec = PieceSpec.from_mm("Estante", 3, "563.6", "399.9", 18)
    project.furniture[0].pieces.append(spec)
    loaded = service.open(service.save(project).id)
    piece = loaded.all_piece_specs()[0]
    assert (str(piece.width_mm), str(piece.height_mm)) == ("563.6", "399.9")
    assert replace(piece, id=None) == spec
