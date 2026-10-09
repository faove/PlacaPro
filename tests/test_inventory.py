"""Confirmar un plan de corte: descuenta stock y consume retazos, todo o nada."""

from dataclasses import replace

import pytest

from database.repositories import ResultRepository
from models.parametros import CuttingParameters, OptimizationLevel
from models.resultado import OptimizationResult, SheetLayout, SheetSource
from models.retazo import Offcut, OffcutStatus
from services.inventory_service import ConfirmationError, InventoryService
from services.optimization_service import OptimizationService
from tests.test_optimization_service import demo


def saved_result(db, project_id, *sheets) -> OptimizationResult:
    return ResultRepository(db).save(
        OptimizationResult(CuttingParameters(), sheets=tuple(sheets), project_id=project_id)
    )


def sheet(index, source, plate_format_id=None, source_offcut_id=None) -> SheetLayout:
    return SheetLayout(
        index,
        10000,
        10000,
        180,
        source=source,
        plate_format_id=plate_format_id,
        source_offcut_id=source_offcut_id,
    )


def test_confirm_plan_discounts_stock_once(db):
    project = demo(db)
    inventory = InventoryService(db)
    inventory.set_available_plates(project.plate_format_id, 3)
    project.params = replace(project.params, use_stock_first=True, level=OptimizationLevel.FAST)
    result = OptimizationService(db).optimize(project, time_budget_s=1).result
    assert result.stock_plates_used() == {project.plate_format_id: 1}

    confirmed = inventory.confirm_result(result.id)
    assert confirmed.is_confirmed
    assert inventory.available_plates(project.plate_format_id) == 2
    assert inventory.results.get(result.id).is_confirmed  # persistido

    with pytest.raises(ConfirmationError, match="ya fue confirmado"):
        inventory.confirm_result(result.id)
    assert inventory.available_plates(project.plate_format_id) == 2


def test_confirm_never_leaves_negative_stock(db):
    project = demo(db)
    inventory = InventoryService(db)
    inventory.set_available_plates(project.plate_format_id, 1)
    result = saved_result(
        db,
        project.id,
        sheet(0, SheetSource.STOCK, project.plate_format_id),
        sheet(1, SheetSource.STOCK, project.plate_format_id),
    )
    with pytest.raises(ConfirmationError, match="solo quedan 1"):
        inventory.confirm_result(result.id)
    assert inventory.available_plates(project.plate_format_id) == 1
    assert not inventory.results.get(result.id).is_confirmed
    with pytest.raises(ValueError):
        inventory.set_available_plates(project.plate_format_id, -1)


def test_confirm_is_atomic(db):
    """Si un retazo ya no está disponible no se descuenta nada (ni las placas)."""
    project = demo(db)
    inventory = InventoryService(db)
    inventory.set_available_plates(project.plate_format_id, 2)
    offcut = inventory.store_offcut(Offcut(5000, 4000, 180, OffcutStatus.REUSABLE))
    result = saved_result(
        db,
        project.id,
        sheet(0, SheetSource.OFFCUT, source_offcut_id=offcut.id),
        sheet(1, SheetSource.STOCK, project.plate_format_id),
    )
    inventory.mark_offcut_consumed(offcut.id)
    with pytest.raises(ConfirmationError, match="ya no está disponible"):
        inventory.confirm_result(result.id)
    assert inventory.available_plates(project.plate_format_id) == 2

    inventory.offcuts.set_status(offcut.id, OffcutStatus.IN_STOCK)
    inventory.confirm_result(result.id)
    assert inventory.available_plates(project.plate_format_id) == 1
    assert inventory.offcuts.get(offcut.id).status is OffcutStatus.CONSUMED


def test_result_without_stock_confirms_without_changes(db):
    project = demo(db)
    inventory = InventoryService(db)
    inventory.set_available_plates(project.plate_format_id, 4)
    result = saved_result(db, project.id, sheet(0, SheetSource.NEW, project.plate_format_id))
    assert inventory.confirm_result(result.id).is_confirmed
    assert inventory.available_plates(project.plate_format_id) == 4
