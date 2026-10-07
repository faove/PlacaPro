import sqlite3
from dataclasses import replace

import pytest

from database.database import Database
from database.models import SCHEMA_VERSION
from database.repositories import (
    InsufficientStockError,
    MaterialRepository,
    NotFoundError,
    OffcutRepository,
    PlateFormatRepository,
    ProjectRepository,
    ResultRepository,
    StockRepository,
    SupplierRepository,
)
from models.parametros import CuttingParameters, OptimizationLevel
from models.pieza import GrainDirection, PieceCategory, PieceSpec
from models.placa import Material, MaterialKind, PlateFormat, PlateGrain, Supplier
from models.proyecto import Furniture, FurnitureDimensions, Project
from models.resultado import OptimizationResult, Placement, SheetLayout
from models.retazo import Offcut, OffcutStatus


@pytest.fixture
def plate(db):
    return PlateFormatRepository(db).save(PlateFormat.from_mm("Melamina blanca", 1830, 2820, 18))


def big_project(plate_id):
    """2 muebles, 10 piezas distintas."""

    def p(i, **kw):
        return PieceSpec.from_mm(f"Pieza {i}", i, 100 + i, 200 + i, 18, **kw)

    return Project(
        name="Cocina",
        description="Bajo mesada + alacena",
        plate_format_id=plate_id,
        params=CuttingParameters(kerf=40, level=OptimizationLevel.MAX),
        furniture=[
            Furniture(
                "Bajo mesada",
                [p(i, category=PieceCategory.LATERAL) for i in range(1, 6)],
                dimensions=FurnitureDimensions(12000, 8500, 6000),
            ),
            Furniture(
                "Alacena",
                [p(i, grain=GrainDirection.VERTICAL, can_rotate=False) for i in range(6, 11)],
                generator_id="manual",
                generator_params={"estantes": 2},
            ),
        ],
    )


class TestDatabase:
    def test_migrate_is_idempotent(self):
        database = Database(":memory:")
        assert database.migrate() == SCHEMA_VERSION
        assert database.migrate() == SCHEMA_VERSION

    def test_file_database_persists(self, tmp_path):
        path = tmp_path / "sub" / "test.db"
        database = Database(path)
        database.migrate()
        MaterialRepository(database).save(Material("Melamina"))
        database.close()
        reopened = Database(path)
        assert reopened.migrate() == SCHEMA_VERSION
        assert [m.name for m in MaterialRepository(reopened).list()] == ["Melamina"]
        reopened.close()

    def test_foreign_keys_enforced(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO furniture (project_id, name) VALUES (999, 'x')")

    def test_transaction_rollback(self, db):
        repo = MaterialRepository(db)
        with pytest.raises(RuntimeError), db.transaction():
            repo.save(Material("A"))
            raise RuntimeError
        assert repo.list() == []

    def test_nested_transaction_rolls_back_only_inner(self, db):
        repo = MaterialRepository(db)
        with db.transaction():
            repo.save(Material("Outer"))
            with pytest.raises(RuntimeError), db.transaction():
                repo.save(Material("Inner"))
                raise RuntimeError
        assert [m.name for m in repo.list()] == ["Outer"]


class TestPlates:
    def test_crud(self, db):
        repo = PlateFormatRepository(db)
        saved = repo.save(
            PlateFormat.from_mm(
                "Roble",
                2750,
                1830,
                18,
                grain=PlateGrain.ALONG_WIDTH,
                color="Roble",
                price_cents=4500000,
            )
        )
        assert saved.id is not None
        assert repo.get(saved.id) == saved
        updated = repo.save(replace(saved, name="Roble natural"))
        assert repo.get(saved.id).name == "Roble natural" == updated.name
        repo.delete(saved.id)
        with pytest.raises(NotFoundError):
            repo.get(saved.id)

    def test_update_missing_raises(self, db):
        with pytest.raises(NotFoundError):
            PlateFormatRepository(db).save(PlateFormat.from_mm("X", 1, 1, 1, id=42))

    def test_db_rejects_non_positive_dimensions(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            PlateFormatRepository(db).save(PlateFormat("X", 0, 100, 10))

    def test_material_and_supplier(self, db, plate):
        material = MaterialRepository(db).save(Material("MDF", MaterialKind.MDF))
        supplier = SupplierRepository(db).save(Supplier("Maderera Sur", "tel 123"))
        repo = PlateFormatRepository(db)
        repo.save(replace(plate, material_id=material.id, supplier_id=supplier.id))
        assert repo.get(plate.id).supplier_id == supplier.id
        SupplierRepository(db).delete(supplier.id)
        assert repo.get(plate.id).supplier_id is None  # ON DELETE SET NULL


class TestStock:
    def test_quantities(self, db, plate):
        stock = StockRepository(db)
        assert stock.get_quantity(plate.id) == 0
        stock.set_quantity(plate.id, 5)
        assert stock.add(plate.id, 2) == 7
        assert stock.consume(plate.id, 3) == 4
        assert [s.quantity for s in stock.list()] == [4]

    def test_cannot_consume_more_than_available(self, db, plate):
        stock = StockRepository(db)
        stock.set_quantity(plate.id, 1)
        with pytest.raises(InsufficientStockError):
            stock.consume(plate.id, 2)
        assert stock.get_quantity(plate.id) == 1
        with pytest.raises(ValueError):
            stock.set_quantity(plate.id, -1)


class TestProjects:
    def test_round_trip_full_aggregate(self, db, plate):
        repo = ProjectRepository(db)
        saved = repo.save(big_project(plate.id))
        assert saved.id is not None and saved.created_at is not None
        assert all(p.id is not None for p in saved.all_piece_specs())
        loaded = repo.get(saved.id)
        assert loaded == saved
        assert len(loaded.all_piece_specs()) == 10
        assert loaded.furniture[1].generator_params == {"estantes": 2}

    def test_update_replaces_pieces(self, db, plate):
        repo = ProjectRepository(db)
        project = repo.save(big_project(plate.id))
        project.furniture[0].pieces.pop()
        project.name = "Cocina v2"
        repo.save(project)
        loaded = repo.get(project.id)
        assert loaded.name == "Cocina v2"
        assert len(loaded.all_piece_specs()) == 9
        assert db.query_one("SELECT COUNT(*) AS n FROM pieces")["n"] == 9  # sin huérfanas

    def test_draft_with_invalid_piece_can_be_saved(self, db, plate):
        project = Project("Borrador", furniture=[Furniture("B", [PieceSpec("", 0, 0, 0, 0)])])
        loaded = ProjectRepository(db).get(ProjectRepository(db).save(project).id)
        assert loaded.all_piece_specs()[0].quantity == 0

    def test_list_duplicate_delete(self, db, plate):
        repo = ProjectRepository(db)
        original = repo.save(big_project(plate.id))
        copy = repo.duplicate(original.id, "Cocina copia")
        assert copy.id != original.id
        assert repo.get(copy.id).all_piece_specs()[0].name == "Pieza 1"
        summaries = {s.name: s for s in repo.list()}
        assert summaries["Cocina"].piece_count == sum(range(1, 11))
        repo.delete(original.id)
        assert not repo.exists(original.id) and repo.exists(copy.id)
        assert (
            db.query_one(
                "SELECT COUNT(*) AS n FROM furniture WHERE project_id = ?", (original.id,)
            )["n"]
            == 0
        )
        with pytest.raises(NotFoundError):
            repo.delete(original.id)

    def test_deleting_plate_unsets_project_plate(self, db, plate):
        project = ProjectRepository(db).save(big_project(plate.id))
        PlateFormatRepository(db).delete(plate.id)
        assert ProjectRepository(db).get(project.id).plate_format_id is None


class TestResults:
    def test_save_latest_list(self, db, plate):
        project = ProjectRepository(db).save(big_project(plate.id))
        piece = project.piece_instances()[0]
        sheet = SheetLayout(
            0,
            plate.width,
            plate.height,
            plate.thickness,
            placements=(Placement(piece, 0, 100, 100, piece.width, piece.height),),
        )
        repo = ResultRepository(db)
        first = repo.save(
            OptimizationResult(
                CuttingParameters(), (sheet,), strategy="a", score=(1, 2), project_id=project.id
            )
        )
        second = repo.save(replace(first, id=None, created_at=None, strategy="b"))
        assert repo.get(first.id) == first
        assert repo.latest(project.id).strategy == "b"
        assert [s.id for s in repo.list(project.id)] == [second.id, first.id]
        ProjectRepository(db).delete(project.id)
        assert repo.latest(project.id) is None

    def test_result_requires_project(self, db):
        with pytest.raises(ValueError):
            ResultRepository(db).save(OptimizationResult(CuttingParameters()))


class TestOffcuts:
    def test_filters_and_status(self, db, plate):
        repo = OffcutRepository(db)
        a = repo.save(Offcut(6000, 4000, 180, OffcutStatus.IN_STOCK, plate.id))
        repo.save(Offcut(3000, 3000, 180, OffcutStatus.IN_STOCK, plate.id))
        repo.save(Offcut(6000, 4000, 150, OffcutStatus.IN_STOCK))
        assert len(repo.list(OffcutStatus.IN_STOCK, thickness=180)) == 2
        assert repo.list(OffcutStatus.IN_STOCK)[0].area == 24_000_000  # mayores primero
        repo.set_status(a.id, OffcutStatus.CONSUMED)
        assert repo.get(a.id).status is OffcutStatus.CONSUMED
        assert len(repo.list(OffcutStatus.IN_STOCK)) == 2
        repo.delete(a.id)
        with pytest.raises(NotFoundError):
            repo.set_status(a.id, OffcutStatus.IN_STOCK)
