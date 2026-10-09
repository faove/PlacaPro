"""Contrato de los exportadores y registro.

Para añadir un formato basta con un módulo nuevo que defina una clase con los atributos
de ``Exporter`` y la registre con ``register(...)``; ``exporters/__init__.py`` lo importa
y el menú Archivo ▸ Exportar se genera a partir de ``EXPORTERS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from models.pieza import PieceSpec
from models.placa import PlateFormat
from models.proyecto import Project
from models.resultado import OptimizationResult
from utils.units import Unit


@dataclass(frozen=True)
class ExportContext:
    """Todo lo que necesita un exportador; lo arma ``services.report_service``."""

    project: Project
    result: OptimizationResult
    plate: PlateFormat | None = None
    pieces: tuple[tuple[str, PieceSpec], ...] = ()
    """Despiece del proyecto: (nombre del mueble, pieza)."""
    material_names: dict[int, str] = field(default_factory=dict)
    unit: Unit = Unit.MM
    generated_at: datetime = field(default_factory=datetime.now)

    def material_name(self, material_id: int | None) -> str:
        if material_id is None:
            return ""
        return self.material_names.get(material_id, f"#{material_id}")


class Exporter(Protocol):
    id: str
    """Identificador estable (``"pdf"``, ``"csv"``…)."""
    name: str
    """Texto del menú."""
    file_filter: str
    """Filtro de ``QFileDialog`` («PDF (*.pdf)»)."""
    suffix: str
    """Extensión del archivo principal, con punto."""
    menu_order: int
    """Posición en el menú (menor primero)."""

    def export(self, context: ExportContext, path: Path) -> list[Path]:
        """Escribe el/los archivo(s) y devuelve sus rutas."""
        ...


EXPORTERS: dict[str, Exporter] = {}


def register(exporter: Exporter) -> Exporter:
    if exporter.id in EXPORTERS:
        raise ValueError(f"Ya hay un exportador con id «{exporter.id}»")
    EXPORTERS[exporter.id] = exporter
    return exporter


def exporters_in_menu_order() -> list[Exporter]:
    return sorted(EXPORTERS.values(), key=lambda e: (e.menu_order, e.name))


def get_exporter(exporter_id: str) -> Exporter:
    try:
        return EXPORTERS[exporter_id]
    except KeyError:
        raise LookupError(f"No existe el exportador «{exporter_id}»") from None
