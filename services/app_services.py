"""Servicios de la aplicación construidos sobre una misma base (inyección manual)."""

from __future__ import annotations

from dataclasses import dataclass

from database.database import Database
from services.inventory_service import InventoryService
from services.optimization_service import OptimizationService
from services.plate_service import PlateService
from services.project_service import ProjectService
from services.report_service import ReportService


@dataclass(frozen=True)
class AppServices:
    db: Database
    projects: ProjectService
    plates: PlateService
    inventory: InventoryService
    optimization: OptimizationService
    reports: ReportService

    @classmethod
    def from_db(cls, db: Database) -> AppServices:
        return cls(
            db=db,
            projects=ProjectService(db),
            plates=PlateService(db),
            inventory=InventoryService(db),
            optimization=OptimizationService(db),
            reports=ReportService(db),
        )
