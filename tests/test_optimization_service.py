from dataclasses import replace

from database.seed import seed
from models.parametros import OptimizationLevel
from models.pieza import PieceSpec
from models.resultado import SheetSource
from models.retazo import Offcut, OffcutStatus
from models.validation import IssueCode
from services.inventory_service import InventoryService
from services.optimization_service import OptimizationService
from services.project_service import ProjectService


def demo(db):
    return ProjectService(db).open(seed(db).demo_project_id)


def test_demo_end_to_end_and_saved(db):
    project = demo(db)
    service = OptimizationService(db)
    outcome = service.optimize(project)
    assert outcome.ok and outcome.report.errors == []
    result = outcome.result
    assert result.sheets_count == 1 and result.pieces_count == 7
    assert result.id is not None and result.project_id == project.id
    assert service.latest_result(project.id) == result


def test_invalid_project_is_not_optimized(db):
    project = demo(db)
    project.furniture[0].pieces.append(PieceSpec.from_mm("Rota", 0, 100, 100, 18))
    outcome = OptimizationService(db).optimize(project)
    assert not outcome.ok
    assert IssueCode.ZERO_QUANTITY in outcome.report.codes()


def test_oversized_piece_blocks_optimization(db):
    project = demo(db)
    project.furniture[0].pieces.append(
        PieceSpec.from_mm("Enorme", 1, 2000, 3000, 18, can_rotate=False)
    )
    outcome = OptimizationService(db).optimize(project)
    assert not outcome.ok
    assert IssueCode.PIECE_LARGER_THAN_PLATE in outcome.report.codes()


def test_unsaved_project_is_not_persisted(db):
    project = demo(db)
    project = project.duplicate("Sin guardar")
    outcome = OptimizationService(db).optimize(project)
    assert outcome.ok and outcome.result.id is None


def test_stock_and_offcuts_first(db):
    project = demo(db)
    project.params = replace(
        project.params,
        use_stock_first=True,
        use_offcuts_first=True,
        level=OptimizationLevel.FAST,
    )
    inventory = InventoryService(db)
    inventory.set_available_plates(project.plate_format_id, 3)
    # retazo donde caben las dos puertas (282 × 600) con kerf
    inventory.store_offcut(Offcut(5700, 6000, 180, OffcutStatus.REUSABLE))
    # retazo de otro espesor: no debe usarse
    inventory.store_offcut(Offcut(9000, 9000, 150, OffcutStatus.REUSABLE))
    result = OptimizationService(db).optimize(project).result
    sources = [s.source for s in result.sheets]
    assert SheetSource.OFFCUT in sources and SheetSource.STOCK in sources
    assert SheetSource.NEW not in sources
    offcut_sheet = next(s for s in result.sheets if s.source is SheetSource.OFFCUT)
    assert offcut_sheet.thickness == 180


def test_compute_runs_in_another_thread_without_the_database(db):
    """La UI ejecuta ``compute`` en un hilo de trabajo: no debe tocar la conexión SQLite
    (sqlite3 la rechaza fuera del hilo que la creó)."""
    import threading

    from services.optimization_service import OptimizationOutcome, PreparedOptimization

    project = demo(db)
    service = OptimizationService(db)
    prepared = service.prepare(project)
    assert isinstance(prepared, PreparedOptimization)

    box = {}
    thread = threading.Thread(target=lambda: box.update(result=service.compute(prepared)))
    thread.start()
    thread.join()
    outcome = service.finish(prepared, box["result"])
    assert outcome.ok and outcome.result.id is not None
    assert outcome.result.project_id == project.id

    project.furniture[0].pieces.clear()
    invalid = service.prepare(project)
    assert isinstance(invalid, OptimizationOutcome) and not invalid.ok
