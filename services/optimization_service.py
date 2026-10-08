"""Caso de uso «OPTIMIZAR CORTES».

validar → despiece (generador de cada mueble) → expandir cantidades → optimizar →
verificar invariantes → plan de corte y retazos de cada placa → guardar el resultado.

Para la UI el caso de uso se parte en tres pasos: ``prepare`` y ``finish`` usan la base
(hilo principal) y ``compute`` es puro (hilo de trabajo; ver ADR-006).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from database.database import Database
from database.repositories import PlateFormatRepository, ResultRepository
from models.pieza import PieceSpec, expand_pieces
from models.placa import PlateFormat
from models.proyecto import Project
from models.resultado import OptimizationResult
from models.validation import IssueCode, Severity, ValidationIssue, ValidationReport
from optimization.cutting import plan_result
from optimization.optimizer import CancellationToken, OptimizationRequest, Optimizer
from optimization.scoring import Score
from optimization.verification import verify_result
from services.furniture_generator import get_generator
from services.inventory_service import InventoryService
from services.project_service import ProjectService


class OptimizationError(RuntimeError):
    """El resultado violó un invariante: es un error del programa, nunca del usuario."""


@dataclass(frozen=True)
class OptimizationOutcome:
    report: ValidationReport
    result: OptimizationResult | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None


@dataclass(frozen=True)
class PreparedOptimization:
    """Petición validada, lista para ejecutarse fuera del hilo principal."""

    report: ValidationReport
    plate: PlateFormat
    request: OptimizationRequest
    project_id: int | None


class OptimizationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.projects = ProjectService(db)
        self.plates = PlateFormatRepository(db)
        self.results = ResultRepository(db)
        self.inventory = InventoryService(db)

    def piece_specs(self, project: Project, plate: PlateFormat) -> list[PieceSpec]:
        """Despiece de todos los muebles a través de su generador."""
        specs: list[PieceSpec] = []
        for item in project.furniture:
            specs.extend(get_generator(item.generator_id).generate(item, plate.thickness))
        return specs

    def build_request(self, project: Project, plate: PlateFormat) -> OptimizationRequest:
        params = project.params
        stock = self.inventory.available_plates(plate.id) if plate.id is not None else 0
        offcuts = (
            [
                o
                for o in self.inventory.available_offcuts(thickness=plate.thickness)
                if plate.material_id is None
                or o.material_id is None
                or o.material_id == plate.material_id
            ]
            if params.use_offcuts_first
            else []
        )
        pieces = expand_pieces(self.piece_specs(project, plate))
        return OptimizationRequest(pieces, plate, params, stock, offcuts)

    def prepare(self, project: Project) -> PreparedOptimization | OptimizationOutcome:
        """Valida y arma la petición (usa la base: llamar desde el hilo principal).

        Devuelve un ``OptimizationOutcome`` sin resultado si la validación encontró errores.
        """
        report = self.projects.validate(project)
        if report.has_errors:
            return OptimizationOutcome(report)
        plate = self.plates.get(project.plate_format_id)  # type: ignore[arg-type]
        return PreparedOptimization(report, plate, self.build_request(project, plate), project.id)

    @staticmethod
    def compute(
        prepared: PreparedOptimization,
        *,
        cancel: CancellationToken | None = None,
        on_progress: Callable[[float, Score | None], None] | None = None,
        time_budget_s: float | None = None,
    ) -> OptimizationResult:
        """Optimiza, verifica y planifica los cortes. No toca la base: apto para un hilo de
        trabajo. Lanza ``OptimizationCancelled`` si se cancela antes de tener una solución."""
        request = prepared.request
        result = Optimizer(
            request, cancel=cancel, on_progress=on_progress, time_budget_s=time_budget_s
        ).run()
        violations = verify_result(result, request.pieces, prepared.plate.grain)
        if violations:
            detail = "; ".join(v.message for v in violations[:5])
            raise OptimizationError(f"El resultado no supera la verificación: {detail}")
        return plan_result(result, prepared.plate.material_id)

    def finish(
        self, prepared: PreparedOptimization, result: OptimizationResult, *, save: bool = True
    ) -> OptimizationOutcome:
        """Añade los avisos de piezas no ubicadas y guarda el resultado (hilo principal)."""
        report = ValidationReport(list(prepared.report.issues))
        for unplaced in result.unplaced:
            report.issues.append(
                ValidationIssue(IssueCode.UNPLACEABLE_PIECE, Severity.WARNING, unplaced.reason)
            )
        if save and prepared.project_id is not None:
            result = self.results.save(replace(result, project_id=prepared.project_id))
        return OptimizationOutcome(report, result)

    def optimize(
        self,
        project: Project,
        *,
        cancel: CancellationToken | None = None,
        on_progress: Callable[[float, Score | None], None] | None = None,
        time_budget_s: float | None = None,
        save: bool = True,
    ) -> OptimizationOutcome:
        """``prepare`` → ``compute`` → ``finish`` en el hilo actual."""
        prepared = self.prepare(project)
        if isinstance(prepared, OptimizationOutcome):
            return prepared
        result = self.compute(
            prepared, cancel=cancel, on_progress=on_progress, time_budget_s=time_budget_s
        )
        return self.finish(prepared, result, save=save)

    def latest_result(self, project_id: int) -> OptimizationResult | None:
        return self.results.latest(project_id)
