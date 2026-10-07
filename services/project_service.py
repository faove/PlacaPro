"""Casos de uso de proyectos: nuevo, abrir, guardar, guardar como, duplicar, eliminar."""

from __future__ import annotations

from database.database import Database
from database.repositories import PlateFormatRepository, ProjectRepository, ProjectSummary
from models.parametros import CuttingParameters
from models.proyecto import Furniture, Project
from models.validation import (
    IssueCode,
    Severity,
    ValidationFailed,
    ValidationIssue,
    ValidationReport,
    validate_project,
)


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.plates = PlateFormatRepository(db)

    def new_project(
        self,
        name: str = "Proyecto nuevo",
        plate_format_id: int | None = None,
        params: CuttingParameters | None = None,
    ) -> Project:
        """Crea un proyecto en memoria (sin guardar) con un mueble vacío."""
        return Project(
            name=name,
            plate_format_id=plate_format_id,
            params=params or CuttingParameters(),
            furniture=[Furniture(name=name)],
        )

    def list_projects(self) -> list[ProjectSummary]:
        return self.projects.list()

    def open(self, project_id: int) -> Project:
        return self.projects.get(project_id)

    def save(self, project: Project) -> Project:
        """Guarda el proyecto (solo exige un nombre; las piezas pueden estar incompletas)."""
        if not project.name.strip():
            raise ValidationFailed(
                ValidationReport(
                    [
                        ValidationIssue(
                            IssueCode.EMPTY_NAME,
                            Severity.ERROR,
                            "El proyecto debe tener un nombre",
                            field="name",
                        )
                    ]
                )
            )
        project.name = project.name.strip()
        return self.projects.save(project)

    def save_as(self, project: Project, new_name: str) -> Project:
        """Guarda una copia con otro nombre; el original no se modifica."""
        return self.save(project.duplicate(new_name))

    def duplicate(self, project_id: int, new_name: str | None = None) -> Project:
        original = self.projects.get(project_id)
        return self.save(original.duplicate(new_name or f"{original.name} (copia)"))

    def delete(self, project_id: int) -> None:
        self.projects.delete(project_id)

    def validate(self, project: Project) -> ValidationReport:
        """Validación completa previa a la optimización."""
        plate = None
        if project.plate_format_id is not None:
            try:
                plate = self.plates.get(project.plate_format_id)
            except LookupError:
                plate = None
        return validate_project(project, plate)
