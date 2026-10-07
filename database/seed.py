"""Datos iniciales: materiales, formatos estándar de placa y el proyecto demo.

Se ejecuta una sola vez por base de datos (marca ``seed_version`` en ``app_meta``):
si el usuario borra la demo o un formato, no se vuelven a crear.
"""

from __future__ import annotations

from dataclasses import dataclass

from database.database import Database
from database.repositories import (
    MaterialRepository,
    MetaRepository,
    PlateFormatRepository,
    ProjectRepository,
)
from models.pieza import PieceCategory, PieceSpec
from models.placa import Material, MaterialKind, PlateFormat
from models.proyecto import Furniture, Project
from utils.constants import STANDARD_PLATE_FORMATS

SEED_VERSION = "1"
SEED_KEY = "seed_version"
DEMO_PROJECT_KEY = "demo_project_id"
DEMO_PROJECT_NAME = "Mesita de noche"

DEFAULT_MATERIALS: tuple[Material, ...] = (
    Material("Melamina", MaterialKind.MELAMINA),
    Material("MDF", MaterialKind.MDF),
    Material("Fenólico", MaterialKind.FENOLICO),
    Material("Madera maciza", MaterialKind.MADERA_MACIZA),
    Material("Aglomerado", MaterialKind.AGLOMERADO),
)


@dataclass(frozen=True)
class SeedResult:
    seeded: bool
    """True si se insertaron datos en esta llamada."""
    demo_project_id: int | None


def build_demo_project(plate: PlateFormat) -> Project:
    """Proyecto «Mesita de noche» del enunciado (requisito 28)."""
    t = plate.thickness_mm
    mid = plate.material_id
    pieces = [
        PieceSpec.from_mm(
            "Lateral", 2, 400, 600, t, category=PieceCategory.LATERAL, material_id=mid
        ),
        PieceSpec.from_mm("Tapa", 1, 564, 400, t, category=PieceCategory.TAPA, material_id=mid),
        PieceSpec.from_mm("Fondo", 1, 564, 600, t, category=PieceCategory.FONDO, material_id=mid),
        PieceSpec.from_mm("Puerta", 2, 282, 600, t, category=PieceCategory.PUERTA, material_id=mid),
        PieceSpec.from_mm("Zócalo", 1, 564, 100, t, category=PieceCategory.ZOCALO, material_id=mid),
    ]
    return Project(
        name=DEMO_PROJECT_NAME,
        description="Proyecto de demostración",
        plate_format_id=plate.id,
        furniture=[Furniture(name=DEMO_PROJECT_NAME, pieces=pieces)],
    )


def seed(db: Database) -> SeedResult:
    """Inserta los datos iniciales si la base aún no fue inicializada."""
    meta = MetaRepository(db)
    if meta.get(SEED_KEY) is not None:
        demo = meta.get(DEMO_PROJECT_KEY)
        demo_id = int(demo) if demo else None
        if demo_id is not None and not ProjectRepository(db).exists(demo_id):
            demo_id = None
        return SeedResult(False, demo_id)

    with db.transaction():
        materials = MaterialRepository(db)
        melamina = None
        for material in DEFAULT_MATERIALS:
            saved = materials.get_by_name(material.name) or materials.save(material)
            if material.kind is MaterialKind.MELAMINA:
                melamina = saved

        plates = PlateFormatRepository(db)
        saved_plates = [
            plates.save(
                PlateFormat.from_mm(
                    fmt.name,
                    fmt.width_mm,
                    fmt.height_mm,
                    fmt.thickness_mm,
                    material_id=melamina.id if melamina else None,
                    color="Blanco",
                )
            )
            for fmt in STANDARD_PLATE_FORMATS
        ]

        demo = ProjectRepository(db).save(build_demo_project(saved_plates[0]))
        meta.set(DEMO_PROJECT_KEY, str(demo.id))
        meta.set(SEED_KEY, SEED_VERSION)
    return SeedResult(True, demo.id)
