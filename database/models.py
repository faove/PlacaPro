"""Esquema SQLite y migraciones.

Convenciones: sufijo ``_dmm`` = décimas de milímetro (enteros); ``_dmm2`` = dmm²;
``_cents`` = centavos. Fechas en ISO 8601. Cada migración se aplica una sola vez
según ``PRAGMA user_version``.
"""

from __future__ import annotations

SCHEMA_V1 = """
CREATE TABLE app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE materials (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    kind  TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE suppliers (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    contact TEXT NOT NULL DEFAULT ''
);

CREATE TABLE plate_formats (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    width_dmm     INTEGER NOT NULL CHECK (width_dmm > 0),
    height_dmm    INTEGER NOT NULL CHECK (height_dmm > 0),
    thickness_dmm INTEGER NOT NULL CHECK (thickness_dmm > 0),
    material_id   INTEGER REFERENCES materials(id) ON DELETE SET NULL,
    color         TEXT NOT NULL DEFAULT '',
    supplier_id   INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    grain         TEXT NOT NULL DEFAULT 'none',
    price_cents   INTEGER,
    created_at    TEXT NOT NULL
);

CREATE TABLE stock_plates (
    plate_format_id INTEGER PRIMARY KEY REFERENCES plate_formats(id) ON DELETE CASCADE,
    quantity        INTEGER NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE projects (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    plate_format_id INTEGER REFERENCES plate_formats(id) ON DELETE SET NULL,
    params_json     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE furniture (
    id                    INTEGER PRIMARY KEY,
    project_id            INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                  TEXT NOT NULL,
    width_dmm             INTEGER,
    height_dmm            INTEGER,
    depth_dmm             INTEGER,
    generator_id          TEXT NOT NULL DEFAULT 'manual',
    generator_params_json TEXT NOT NULL DEFAULT '{}',
    sort_order            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_furniture_project ON furniture(project_id);

-- Las piezas admiten valores inválidos (cantidad 0, medida 0) para poder guardar
-- borradores; la validación de dominio impide optimizarlos.
CREATE TABLE pieces (
    id                INTEGER PRIMARY KEY,
    furniture_id      INTEGER NOT NULL REFERENCES furniture(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    category          TEXT NOT NULL DEFAULT 'otro',
    quantity          INTEGER NOT NULL CHECK (quantity >= 0),
    width_dmm         INTEGER NOT NULL CHECK (width_dmm >= 0),
    height_dmm        INTEGER NOT NULL CHECK (height_dmm >= 0),
    thickness_dmm     INTEGER NOT NULL CHECK (thickness_dmm >= 0),
    material_id       INTEGER REFERENCES materials(id) ON DELETE SET NULL,
    can_rotate        INTEGER NOT NULL DEFAULT 1,
    grain             TEXT NOT NULL DEFAULT 'none',
    fixed_orientation INTEGER NOT NULL DEFAULT 0,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    notes             TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_pieces_furniture ON pieces(furniture_id);

CREATE TABLE optimization_results (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    strategy     TEXT NOT NULL,
    score_json   TEXT NOT NULL,
    sheets_count INTEGER NOT NULL,
    utilization  REAL NOT NULL,
    params_json  TEXT NOT NULL,
    result_json  TEXT NOT NULL,
    duration_ms  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_results_project ON optimization_results(project_id, created_at);

CREATE TABLE offcuts (
    id               INTEGER PRIMARY KEY,
    plate_format_id  INTEGER REFERENCES plate_formats(id) ON DELETE SET NULL,
    width_dmm        INTEGER NOT NULL CHECK (width_dmm > 0),
    height_dmm       INTEGER NOT NULL CHECK (height_dmm > 0),
    thickness_dmm    INTEGER NOT NULL CHECK (thickness_dmm > 0),
    material_id      INTEGER REFERENCES materials(id) ON DELETE SET NULL,
    status           TEXT NOT NULL,
    source_result_id INTEGER REFERENCES optimization_results(id) ON DELETE SET NULL,
    needs_trim       INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    notes            TEXT NOT NULL DEFAULT ''
);

-- Preparadas para costos (sin uso en v1)
CREATE TABLE hardware_items (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    unit_price_cents INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE furniture_hardware (
    furniture_id INTEGER NOT NULL REFERENCES furniture(id) ON DELETE CASCADE,
    hardware_id  INTEGER NOT NULL REFERENCES hardware_items(id) ON DELETE CASCADE,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (furniture_id, hardware_id)
);
"""

MIGRATIONS: tuple[str, ...] = (SCHEMA_V1,)
"""``MIGRATIONS[i]`` lleva la base de la versión ``i`` a la ``i + 1``."""

SCHEMA_VERSION = len(MIGRATIONS)
