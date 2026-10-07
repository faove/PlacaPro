"""Cálculo de costos (preparado; se implementa en una versión futura).

Entidades en ``models/costos.py`` y tablas ``hardware_items`` / ``furniture_hardware``
ya existen. Ver docs/08-roadmap-futuro.md §2.
"""

from __future__ import annotations

from models.costos import CostBreakdown, MaterialCost
from models.proyecto import Project
from models.resultado import OptimizationResult


class CostService:
    def compute(
        self,
        project: Project,
        result: OptimizationResult,
        material_costs: dict[int, MaterialCost] | None = None,
    ) -> CostBreakdown:
        """Costo de placas, desperdicio, herrajes, mano de obra y precio de venta."""
        raise NotImplementedError("El cálculo de costos se implementará en una versión futura")
