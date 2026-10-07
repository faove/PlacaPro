# Sprint 1 — Dominio y persistencia

**Objetivo**: entidades de dominio completas y persistencia SQLite con repositorios, incluyendo datos semilla y la demo.

**Requisitos cubiertos**: RF-01, RF-02, RF-03 (modelo y persistencia), RF-09 (modelo), base de RF-12, preparación de costos (§30) y generador (§16, §32).

## Alcance

### 1. Modelos (`models/`) — ver [02-modelo-de-dominio-y-datos.md](../02-modelo-de-dominio-y-datos.md)
- [ ] `placa.py`: `PlateGrain`, `Material`, `Supplier`, `PlateFormat` (con `usable_area(params)`), `StockPlate`.
- [ ] `pieza.py`: `GrainDirection`, `PieceCategory`, `PieceSpec` (+ `expand()`), `PieceInstance`.
- [ ] `proyecto.py`: `FurnitureDimensions`, `Furniture`, `Project` (+ `all_piece_specs()`, `duplicate(new_name)`).
- [ ] `retazo.py`: `OffcutStatus`, `Offcut`.
- [ ] `parametros.py`: `CuttingParameters`, `OptimizationLevel`, `CutMode` (+ serialización JSON).
- [ ] `resultado.py`: `Placement`, `SheetLayout`, `OptimizationResult` (+ métricas derivadas, `to_dict/from_dict`).
- [ ] `plan_corte.py`: `Cut`, `CutPlan`.
- [ ] `costos.py`: `MaterialCost`, `HardwareItem`, `LaborCost`, `CostBreakdown` (solo entidades).
- [ ] `validation.py`: `Severity`, `ValidationIssue(code, message, field, piece_id)`, `ValidationReport`; validadores puros:
  - dimensiones > 0, cantidad ≥ 1, kerf en [0, 10] mm, margen ≥ 0 y `2·m < min(W, H)`, espesor de pieza = espesor de placa, pieza cabe en alguna orientación permitida.

### 2. Base de datos (`database/`)
- [ ] `models.py`: DDL v1 ([02 §2](../02-modelo-de-dominio-y-datos.md#2-esquema-sqlite-databasemodelspy-versión-1)).
- [ ] `database.py`: `Database(path)` con `connect()`, `transaction()` (context manager), `migrate()` vía `user_version`, `foreign_keys=ON`.
- [ ] `repositories.py`: repositorios de [02 §3](../02-modelo-de-dominio-y-datos.md#3-repositorios-databaserepositoriespy).
- [ ] `seed.py`: materiales (Melamina, MDF, Fenólico, Madera maciza), formatos estándar (1830×2820, 2440×1220, 2750×1830, 2800×2070, 3000×2100 en 18 mm), proyecto demo "Mesita de noche".

### 3. Servicios base (`services/`)
- [ ] `plate_service.py`, `project_service.py` (nuevo, abrir, guardar, guardar como, duplicar, eliminar), `inventory_service.py`.
- [ ] `furniture_generator.py`: `Protocol FurnitureGenerator` + `ManualGenerator` + registry `GENERATORS`.
- [ ] `cost_service.py`: stub con firma `compute(project, result) -> CostBreakdown` documentado como pendiente.

## Tests del sprint
- `test_models.py`: `expand()` (cantidad 2 → `Lateral 1`, `Lateral 2`), validadores (cada código de error).
- `test_repositories.py` (SQLite `:memory:`): CRUD de placas, guardar/cargar proyecto completo, duplicar, eliminar en cascada, stock, retazos, migración idempotente.
- `test_services.py`: flujo nuevo → guardar → abrir → duplicar → eliminar.

## Criterios de aceptación
- Un proyecto con 2 muebles y 10 piezas se guarda y recupera idéntico (igualdad de dataclasses).
- La demo existe tras `seed()` en una DB vacía y no se duplica si se ejecuta dos veces.
- Ningún módulo de `models/` ni `database/` importa PySide6.

## Resultado
_(completar al cerrar el sprint)_
