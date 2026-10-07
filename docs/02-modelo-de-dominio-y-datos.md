# 02 — Modelo de dominio y datos

## 1. Entidades de dominio (`models/`)

Todas son `@dataclass(frozen=True)` salvo las raíces de agregado editables (`Project`, `Furniture`). Dimensiones expuestas en mm (`Decimal`) y convertibles a unidades internas (`int`, décimas de mm).

### Enumeraciones
```python
class GrainDirection(Enum):   # pieza
    VERTICAL = "vertical"      # veta paralela al ALTO de la pieza
    HORIZONTAL = "horizontal"  # veta paralela al ANCHO de la pieza
    NONE = "none"              # indiferente

class PlateGrain(Enum):        # placa
    ALONG_HEIGHT = "along_height"  # veta paralela al alto de la placa (habitual: lado largo)
    ALONG_WIDTH = "along_width"
    NONE = "none"                  # placa lisa/sin veta (melamina blanca)

class PieceCategory(Enum):    # define color en el diagrama
    LATERAL, TAPA, BASE, FONDO, PUERTA, DIVISOR, ESTANTE, CAJON, ZOCALO, OTRO

class OptimizationLevel(Enum): FAST, BALANCED, MAX
class CutMode(Enum): PANEL_SAW, CNC     # escuadradora (guillotina) / CNC (libre)
class OffcutStatus(Enum): REUSABLE, WASTE, IN_STOCK, CONSUMED
```

### Material y placas
| Entidad | Campos |
|---------|--------|
| `Material` | id, nombre (Melamina, MDF, Fenólico, Madera maciza, ...), color, espesores disponibles |
| `Supplier` | id, nombre, contacto (preparado) |
| `PlateFormat` | id, nombre, ancho, alto, espesor, material_id, color, supplier_id, grain: `PlateGrain`, price (opcional) |
| `StockPlate` | plate_format_id, cantidad_disponible |
| `Offcut` | id, plate_format_id (origen), ancho, alto, espesor, material, status, origen (resultado/placa), fecha |

### Proyecto y piezas
| Entidad | Campos |
|---------|--------|
| `Project` | id, nombre, descripción, fecha_creación, fecha_modificación, plate_format_id seleccionado, `CuttingParameters`, lista de `Furniture` |
| `Furniture` | id, nombre ("Mesita de noche"), `FurnitureDimensions` (ancho, alto, profundidad — opcional), generator_id (`"manual"` por defecto), lista de `PieceSpec` |
| `PieceSpec` | id, nombre, categoría, cantidad, ancho, alto, espesor, material_id, can_rotate: bool, grain: `GrainDirection`, fixed_orientation: bool, notas |
| `PieceInstance` | spec_id, índice (1..cantidad), etiqueta (`"Lateral 2"`), ancho, alto, orientaciones permitidas |

`PieceSpec.expand() -> list[PieceInstance]` convierte cantidades a piezas individuales (requisito 5).

### Parámetros
```python
@dataclass(frozen=True)
class CuttingParameters:
    kerf: Decimal = Decimal("3.2")
    edge_margin: Decimal = Decimal("10")        # refilado por cada borde
    extra_spacing: Decimal = Decimal("0")       # separación adicional entre piezas
    allow_rotation: bool = True                 # global; se combina con la pieza
    level: OptimizationLevel = OptimizationLevel.BALANCED
    cut_mode: CutMode = CutMode.PANEL_SAW
    use_stock_first: bool = False
    use_offcuts_first: bool = False
    min_offcut_width: Decimal = Decimal("150")
    min_offcut_height: Decimal = Decimal("150")
    min_offcut_area_m2: Decimal = Decimal("0.05")
    seed: int = 42
```

### Resultado
| Entidad | Campos |
|---------|--------|
| `Placement` | piece_instance, sheet_index, x, y, placed_width, placed_height, rotated: bool |
| `SheetLayout` | sheet_index, source (nueva / inventario / retazo), ancho, alto, placements, used_area, waste_area, utilization, offcuts, cut_plan |
| `Cut` | orden, orientation (horizontal/vertical), posición, longitud, nivel (1° tira, 2°, 3°…), región padre |
| `CutPlan` | sheet_index, cuts ordenados, total_cuts, total_cut_length |
| `OptimizationResult` | id, project_id, fecha, params, sheets, unplaced (piezas sin ubicar), score, strategy_name, duración_ms, métricas globales |

Métricas globales: `sheets_count`, `total_area`, `used_area`, `waste_area`, `reusable_offcut_area`, `utilization`, `pieces_count`.

> **Definición de áreas** (documentarla también en la UI):
> - *Área total* = suma del área nominal de las placas usadas.
> - *Área utilizada* = suma del área neta de las piezas (sin kerf).
> - *Desperdicio* = total − utilizada (incluye kerf, márgenes y retazos).
> - *Desperdicio no aprovechable* = desperdicio − retazos reutilizables.
> - *Aprovechamiento* = utilizada / total.

### Costos (preparado, sin UI en v1)
`MaterialCost` (precio placa, precio m²), `HardwareItem` (herraje, cantidad, precio), `LaborCost` (horas, tarifa), `CostBreakdown` (placas, desperdicio, herrajes, mano de obra, total, precio venta, margen %).

## 2. Esquema SQLite (`database/models.py`, versión 1)

```sql
CREATE TABLE materials (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, notes TEXT);

CREATE TABLE suppliers (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, contact TEXT);

CREATE TABLE plate_formats (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL,
  width_dmm INTEGER NOT NULL CHECK(width_dmm > 0),
  height_dmm INTEGER NOT NULL CHECK(height_dmm > 0),
  thickness_dmm INTEGER NOT NULL CHECK(thickness_dmm > 0),
  material_id INTEGER REFERENCES materials(id),
  color TEXT, supplier_id INTEGER REFERENCES suppliers(id),
  grain TEXT NOT NULL DEFAULT 'none',
  price_cents INTEGER, created_at TEXT NOT NULL);

CREATE TABLE stock_plates (
  plate_format_id INTEGER PRIMARY KEY REFERENCES plate_formats(id) ON DELETE CASCADE,
  quantity INTEGER NOT NULL CHECK(quantity >= 0));

CREATE TABLE projects (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT,
  plate_format_id INTEGER REFERENCES plate_formats(id),
  params_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE furniture (
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL, width_dmm INTEGER, height_dmm INTEGER, depth_dmm INTEGER,
  generator_id TEXT NOT NULL DEFAULT 'manual', generator_params_json TEXT);

CREATE TABLE pieces (
  id INTEGER PRIMARY KEY, furniture_id INTEGER NOT NULL REFERENCES furniture(id) ON DELETE CASCADE,
  name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'otro',
  quantity INTEGER NOT NULL CHECK(quantity > 0),
  width_dmm INTEGER NOT NULL CHECK(width_dmm > 0),
  height_dmm INTEGER NOT NULL CHECK(height_dmm > 0),
  thickness_dmm INTEGER NOT NULL CHECK(thickness_dmm > 0),
  material_id INTEGER REFERENCES materials(id),
  can_rotate INTEGER NOT NULL DEFAULT 1, grain TEXT NOT NULL DEFAULT 'none',
  fixed_orientation INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0, notes TEXT);

CREATE TABLE optimization_results (
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, strategy TEXT NOT NULL, score TEXT NOT NULL,
  sheets_count INTEGER NOT NULL, utilization REAL NOT NULL,
  params_json TEXT NOT NULL, result_json TEXT NOT NULL, duration_ms INTEGER);

CREATE TABLE offcuts (
  id INTEGER PRIMARY KEY, plate_format_id INTEGER REFERENCES plate_formats(id),
  width_dmm INTEGER NOT NULL, height_dmm INTEGER NOT NULL, thickness_dmm INTEGER NOT NULL,
  material_id INTEGER REFERENCES materials(id), status TEXT NOT NULL,
  source_result_id INTEGER REFERENCES optimization_results(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL, notes TEXT);

-- Preparadas para costos (vacías en v1)
CREATE TABLE hardware_items (id INTEGER PRIMARY KEY, name TEXT NOT NULL, unit_price_cents INTEGER);
CREATE TABLE furniture_hardware (furniture_id INTEGER REFERENCES furniture(id) ON DELETE CASCADE,
  hardware_id INTEGER REFERENCES hardware_items(id), quantity INTEGER NOT NULL);
```

Notas:
- Sufijo `_dmm` = décimas de milímetro (enteros). Ver ADR-002.
- Dinero en centavos enteros (`_cents`).
- `PRAGMA foreign_keys = ON` en cada conexión; migraciones por `PRAGMA user_version`.
- Ubicación de la base: `~/.placapro/placapro.db` (configurable por variable `PLACAPRO_DB`; tests usan `:memory:`).

## 3. Repositorios (`database/repositories.py`)

| Repositorio | Métodos principales |
|-------------|---------------------|
| `PlateFormatRepository` | `list()`, `get(id)`, `save(fmt)`, `delete(id)` |
| `StockRepository` | `get_quantity(fmt_id)`, `set_quantity()`, `consume(fmt_id, n)` |
| `ProjectRepository` | `list()`, `get(id)` (agregado completo), `save(project)`, `duplicate(id, new_name)`, `delete(id)` |
| `ResultRepository` | `save(result)`, `latest(project_id)`, `list(project_id)` |
| `OffcutRepository` | `list(status, material, thickness)`, `save()`, `mark_consumed()` |
| `MaterialRepository`, `SupplierRepository` | CRUD básico |

Guardar un proyecto es **transaccional** (proyecto + muebles + piezas en una sola transacción).
