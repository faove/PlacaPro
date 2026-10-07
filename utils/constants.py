"""Constantes de la aplicación. Longitudes en mm (``Decimal``)."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

APP_NAME = "PlacaPro"
APP_VERSION = "0.1.0"
ORGANIZATION = "PlacaPro"


class StandardFormat(NamedTuple):
    name: str
    width_mm: Decimal
    height_mm: Decimal
    thickness_mm: Decimal


STANDARD_PLATE_FORMATS: tuple[StandardFormat, ...] = (
    StandardFormat("Melamina blanca 1830 × 2820", Decimal(1830), Decimal(2820), Decimal(18)),
    StandardFormat("Melamina blanca 2440 × 1220", Decimal(2440), Decimal(1220), Decimal(18)),
    StandardFormat("Melamina blanca 2750 × 1830", Decimal(2750), Decimal(1830), Decimal(18)),
    StandardFormat("Melamina blanca 2800 × 2070", Decimal(2800), Decimal(2070), Decimal(18)),
    StandardFormat("Melamina blanca 3000 × 2100", Decimal(3000), Decimal(2100), Decimal(18)),
)

# Parámetros de corte por defecto
DEFAULT_KERF_MM = Decimal("3.2")
DEFAULT_EDGE_MARGIN_MM = Decimal(10)
DEFAULT_EXTRA_SPACING_MM = Decimal(0)
MAX_KERF_MM = Decimal(10)

# Retazos: mínimos para considerarlos reutilizables
DEFAULT_MIN_OFFCUT_WIDTH_MM = Decimal(150)
DEFAULT_MIN_OFFCUT_HEIGHT_MM = Decimal(150)
DEFAULT_MIN_OFFCUT_AREA_M2 = Decimal("0.05")

DEFAULT_SEED = 42

# Persistencia
DB_ENV_VAR = "PLACAPRO_DB"
APP_DATA_DIR = Path.home() / ".placapro"


def default_db_path() -> Path:
    """Ruta de la base SQLite; se puede sobrescribir con la variable ``PLACAPRO_DB``."""
    override = os.environ.get(DB_ENV_VAR)
    return Path(override) if override else APP_DATA_DIR / "placapro.db"
