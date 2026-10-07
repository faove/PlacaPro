import os
import sys
from pathlib import Path

# Qt sin pantalla para los tests de interfaz.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Permite importar los paquetes del proyecto desde la raíz.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import pytest  # noqa: E402

from database.database import Database  # noqa: E402


@pytest.fixture
def db():
    """Base SQLite en memoria con el esquema aplicado."""
    database = Database(":memory:")
    database.migrate()
    yield database
    database.close()
