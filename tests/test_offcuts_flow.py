"""Ciclo de un retazo: resultado → stock → otra optimización lo usa → consumido."""

from dataclasses import replace

from models.parametros import OptimizationLevel
from models.resultado import SheetSource
from models.retazo import OffcutStatus
from services.inventory_service import InventoryService
from services.optimization_service import OptimizationService
from tests.test_optimization_service import demo


def test_offcut_saved_reused_and_consumed(db):
    project = demo(db)
    service = OptimizationService(db)
    inventory = InventoryService(db)
    project.params = replace(project.params, level=OptimizationLevel.FAST)

    first = service.optimize(project, time_budget_s=1).result
    reusable = [o for s in first.sheets for o in s.offcuts if o.status is OffcutStatus.REUSABLE]
    assert reusable, "la demo deja al menos un retazo reutilizable"
    biggest = max(reusable, key=lambda o: o.area)

    # Guardar en stock → aparece disponible.
    [stored] = inventory.save_offcuts(first.id, [biggest.label])
    available = inventory.available_offcuts()
    assert [o.id for o in available] == [stored.id]
    assert (stored.width, stored.height) == (biggest.width, biggest.height)

    # Otra optimización con «usar retazos» lo usa como placa.
    project.params = replace(project.params, use_offcuts_first=True)
    second = service.optimize(project, time_budget_s=1).result
    assert second.stock_offcuts_used() == [stored.id]
    assert second.sheets[0].source is SheetSource.OFFCUT
    assert inventory.available_offcuts() == [available[0]]  # aún no confirmado

    # Confirmar el plan → consumido y fuera del stock disponible.
    inventory.confirm_result(second.id)
    assert inventory.offcuts.get(stored.id).status is OffcutStatus.CONSUMED
    assert inventory.available_offcuts() == []

    # Una tercera optimización ya no lo encuentra.
    third = service.optimize(project, time_budget_s=1).result
    assert third.stock_offcuts_used() == []
