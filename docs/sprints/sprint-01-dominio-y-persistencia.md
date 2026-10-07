# Sprint 1 — Dominio y persistencia

**Objetivo**: entidades de dominio completas y persistencia SQLite con repositorios, incluyendo datos semilla y la demo.

**Requisitos cubiertos**: RF-01, RF-02, RF-03 (modelo y persistencia), RF-09 (modelo), base de RF-12, preparación de costos (§30) y generador (§16, §32).

## Alcance

### 1. Modelos (`models/`) — ver [02-modelo-de-dominio-y-datos.md](../02-modelo-de-dominio-y-datos.md)
- [x] `placa.py`: `PlateGrain`, `Material`, `Supplier`, `PlateFormat` (con `usable_area(params)`), `StockPlate`.
- [x] `pieza.py`: `GrainDirection`, `PieceCategory`, `PieceSpec` (+ `expand()`), `PieceInstance`.
- [x] `proyecto.py`: `FurnitureDimensions`, `Furniture`, `Project` (+ `all_piece_specs()`, `duplicate(new_name)`).
- [x] `retazo.py`: `OffcutStatus`, `Offcut`.
- [x] `parametros.py`: `CuttingParameters`, `OptimizationLevel`, `CutMode` (+ serialización JSON).
- [x] `resultado.py`: `Placement`, `SheetLayout`, `OptimizationResult` (+ métricas derivadas, `to_dict/from_dict`).
- [x] `plan_corte.py`: `Cut`, `CutPlan`.
- [x] `costos.py`: `MaterialCost`, `HardwareItem`, `LaborCost`, `CostBreakdown` (solo entidades).
- [x] `validation.py`: `Severity`, `ValidationIssue(code, message, field, piece_id)`, `ValidationReport`; validadores puros:
  - dimensiones > 0, cantidad ≥ 1, kerf en [0, 10] mm, margen ≥ 0 y `2·m < min(W, H)`, espesor de pieza = espesor de placa, pieza cabe en alguna orientación permitida.

### 2. Base de datos (`database/`)
- [x] `models.py`: DDL v1 ([02 §2](../02-modelo-de-dominio-y-datos.md#2-esquema-sqlite-databasemodelspy-versión-1)).
- [x] `database.py`: `Database(path)` con `connect()`, `transaction()` (context manager), `migrate()` vía `user_version`, `foreign_keys=ON`.
- [x] `repositories.py`: repositorios de [02 §3](../02-modelo-de-dominio-y-datos.md#3-repositorios-databaserepositoriespy).
- [x] `seed.py`: materiales (Melamina, MDF, Fenólico, Madera maciza), formatos estándar (1830×2820, 2440×1220, 2750×1830, 2800×2070, 3000×2100 en 18 mm), proyecto demo "Mesita de noche".

### 3. Servicios base (`services/`)
- [x] `plate_service.py`, `project_service.py` (nuevo, abrir, guardar, guardar como, duplicar, eliminar), `inventory_service.py`.
- [x] `furniture_generator.py`: `Protocol FurnitureGenerator` + `ManualGenerator` + registry `GENERATORS`.
- [x] `cost_service.py`: stub con firma `compute(project, result) -> CostBreakdown` documentado como pendiente.

## Tests del sprint
- `test_models.py`: `expand()` (cantidad 2 → `Lateral 1`, `Lateral 2`), validadores (cada código de error).
- `test_repositories.py` (SQLite `:memory:`): CRUD de placas, guardar/cargar proyecto completo, duplicar, eliminar en cascada, stock, retazos, migración idempotente.
- `test_services.py`: flujo nuevo → guardar → abrir → duplicar → eliminar.

## Criterios de aceptación
- Un proyecto con 2 muebles y 10 piezas se guarda y recupera idéntico (igualdad de dataclasses).
- La demo existe tras `seed()` en una DB vacía y no se duplica si se ejecuta dos veces.
- Ningún módulo de `models/` ni `database/` importa PySide6.

## Resultado
**Estado: cerrado (2026-10-07).**

### Entregado
- `models/`: `placa.py`, `pieza.py`, `proyecto.py`, `retazo.py`, `parametros.py`, `resultado.py`, `plan_corte.py`, `costos.py`, `validation.py` (+ `_base.py` con utilidades comunes).
- `optimization/orientation.py` (**adelantado del sprint 2**): `allowed_rotations()` lo necesita la validación «pieza mayor que la placa».
- `database/`: `database.py` (transacciones anidables con SAVEPOINT, migraciones por `user_version`), `models.py` (esquema v1), `repositories.py`, `seed.py`.
- `services/`: `plate_service.py`, `project_service.py`, `inventory_service.py`, `furniture_generator.py` (`ManualGenerator` + registro), `cost_service.py` (pendiente; lanza `NotImplementedError`).

### Decisiones y desvíos respecto al plan
- **Medidas en las entidades como `int` (dmm)**, con propiedades `*_mm` y `from_mm()`. Así el optimizador no convierte nada. El doc 02 está actualizado.
- **Las entidades solo validan tipos**: una pieza con cantidad 0 puede existir y guardarse como borrador. `validation.py` informa el problema y bloquea la optimización. Por eso la tabla `pieces` admite `>= 0`; `plate_formats` y `offcuts` siguen exigiendo `> 0`.
- **Veta frente a rotación**: alinear la veta es obligatorio aunque la rotación esté desactivada. Con `fixed_orientation` se respeta lo dibujado y se emite el aviso `GRAIN_CONFLICT`.
- **Etiquetas**: `Lateral 1`, `Lateral 2` cuando la cantidad es mayor que 1; si es 1, solo el nombre (`Tapa`).
- Cambios de esquema respecto al doc 02 (la referencia es `database/models.py`): tabla `app_meta`, `ON DELETE SET NULL` en las referencias a placa, material y proveedor, `offcuts.needs_trim`, `furniture.sort_order`, `score_json`.
- `seed()` se ejecuta **una sola vez por base** (marca en `app_meta`): si el usuario borra la demo, no se vuelve a crear.
- Los formatos estándar se llaman «Melamina blanca 1830 × 2820», etc.

### Verificación
- **146 tests pasan**; cobertura de `models`, `database`, `services`, `optimization` y `utils`: **96 %**.
- Un proyecto con 2 muebles y 10 piezas se guarda y se recupera idéntico; las medidas con decimales (563,6 mm) se conservan exactas.
- Un test comprueba en un subproceso que ningún módulo del núcleo importa PySide6.
- Prueba con una base real en disco: semilla, demo con 7 piezas individuales (1,4388 m² frente a 5,1606 m² de placa) y validación sin problemas.
- `ruff check` y `ruff format --check` limpios (se excluye `docs/`).
