"""Exportación del resultado: arma el ``ExportContext`` y propone nombres de archivo.

Los formatos se cargan al usarlos (``load_exporters``): PDF y SVG necesitan Qt y este
módulo no debe importarlo.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from database.database import Database
from database.repositories import MaterialRepository, PlateFormatRepository
from exporters import ExportContext, Exporter, get_exporter, load_exporters
from models.pieza import PieceSpec
from models.placa import PlateFormat
from models.proyecto import Project
from models.resultado import OptimizationResult
from services.furniture_generator import get_generator
from utils.units import Unit

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_filename(name: str) -> str:
    """Nombre de archivo válido en Windows/Linux/macOS a partir de un texto libre."""
    clean = _UNSAFE.sub("_", name).strip(" .")
    return clean or "proyecto"


class ReportService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.plates = PlateFormatRepository(db)
        self.materials = MaterialRepository(db)

    @staticmethod
    def exporters() -> list[Exporter]:
        return load_exporters()

    def _plate(self, project: Project) -> PlateFormat | None:
        if project.plate_format_id is None:
            return None
        try:
            return self.plates.get(project.plate_format_id)
        except LookupError:
            return None

    def build_context(
        self,
        project: Project,
        result: OptimizationResult,
        *,
        unit: Unit = Unit.MM,
        generated_at: datetime | None = None,
    ) -> ExportContext:
        plate = self._plate(project)
        pieces: list[tuple[str, PieceSpec]] = []
        for item in project.furniture:
            specs = (
                get_generator(item.generator_id).generate(item, plate.thickness)
                if plate is not None
                else item.pieces
            )
            pieces += [(item.name, spec) for spec in specs]
        return ExportContext(
            project=project,
            result=result,
            plate=plate,
            pieces=tuple(pieces),
            material_names={m.id: m.name for m in self.materials.list() if m.id is not None},
            unit=unit,
            generated_at=generated_at or datetime.now(),
        )

    @staticmethod
    def default_filename(project: Project, exporter_id: str) -> str:
        load_exporters()
        exporter = get_exporter(exporter_id)
        return f"{safe_filename(project.name)} - plan de corte{exporter.suffix}"

    def export(
        self,
        exporter_id: str,
        project: Project,
        result: OptimizationResult,
        path: str | Path,
        *,
        unit: Unit = Unit.MM,
    ) -> list[Path]:
        """Exporta y devuelve los archivos escritos."""
        context = self.build_context(project, result, unit=unit)
        load_exporters()
        return get_exporter(exporter_id).export(context, Path(path))
