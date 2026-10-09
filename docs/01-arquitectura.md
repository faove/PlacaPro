# 01 — Arquitectura

## 1. Principios

1. **Dominio puro**: `models/`, `optimization/` y `services/` no importan PySide6. Se pueden testear y reutilizar (CLI, web futura).
2. **Separación optimización matemática ↔ plan de corte físico**: el optimizador produce un *layout* (rectángulos colocados); el planificador de corte produce una *secuencia de cortes ejecutable*. Son módulos distintos con contratos distintos.
3. **Pipeline explícito del mueble** (requisito 32):

```
DescripciónMueble ─► DimensionesMueble ─► Despiece ─► [PiezaSpec] ─► expand() ─► [PiezaInstancia]
      (futuro: generador por reglas)        │
                                            ▼
                    Placa(s) + Inventario + Parámetros ─► Optimizer ─► Layout por placa
                                                                          │
                                                                          ▼
                                                     CuttingPlanner ─► PlanDeCorte + Retazos
                                                                          │
                                                                          ▼
                                                           ResultadoOptimización ─► UI / Exportadores
```

4. **Puertos y adaptadores**: los repositorios (SQLite) y los exportadores (PDF, CSV, futuro DXF/SVG/CNC) implementan interfaces (`Protocol`) definidas en el dominio/servicios.
5. **Estrategias enchufables**: cada algoritmo de packing implementa `PackingStrategy`; cada generador de muebles implementa `FurnitureGenerator`; cada exportador implementa `Exporter`. Registro mediante diccionarios/registries.

## 2. Capas

| Capa | Carpeta | Responsabilidad | Depende de |
|------|---------|-----------------|------------|
| Presentación | `ui/` | Widgets Qt, view-models, hilos de trabajo | services, models |
| Aplicación | `services/` | Casos de uso: guardar proyecto, optimizar, exportar, inventario | models, optimization, database (vía interfaces) |
| Dominio | `models/` | Entidades y value objects inmutables, validaciones | utils |
| Algoritmos | `optimization/` | Packing, scoring, planificación de corte, retazos | models, utils |
| Infraestructura | `database/`, `exporters/` | SQLite, PDF, CSV | models |
| Utilidades | `utils/` | Unidades, geometría, constantes | — |

## 3. Estructura de carpetas

```
PlacaPro/
├── app.py                      # punto de entrada: crea QApplication, DB, servicios, MainWindow
├── requirements.txt
├── README.md
├── pyproject.toml              # config de pytest / ruff
├── docs/
├── database/
│   ├── database.py             # conexión, migraciones (PRAGMA user_version), transacciones
│   ├── models.py               # DDL de tablas (SCHEMA_V1, ...)
│   ├── repositories.py         # PlateRepository, ProjectRepository, OffcutRepository, ...
│   └── seed.py                 # formatos estándar + demo "Mesita de noche"
├── models/
│   ├── placa.py                # PlateFormat, StockPlate, GrainDirection
│   ├── pieza.py                # PieceSpec, PieceInstance, PieceCategory
│   ├── proyecto.py             # Project, Furniture, FurnitureDimensions
│   ├── retazo.py               # Offcut, OffcutStatus
│   ├── parametros.py           # CuttingParameters, OptimizationLevel
│   ├── resultado.py            # Placement, SheetLayout, OptimizationResult
│   ├── plan_corte.py           # Cut, CutPlan, CutOrientation
│   ├── costos.py               # (preparado) MaterialCost, HardwareItem, LaborCost, CostBreakdown
│   └── validation.py           # ValidationIssue, Severity, validadores
├── optimization/
│   ├── optimizer.py            # Optimizer: orquesta estrategias, intentos, selección
│   ├── packing.py              # MaxRectsPacker, GuillotinePacker, SkylinePacker (opcional)
│   ├── orientation.py          # orientaciones permitidas según veta/rotación
│   ├── cutting.py              # CuttingPlanner: árbol guillotina → secuencia de cortes
│   ├── offcuts.py              # detección y clasificación de retazos
│   ├── scoring.py              # Score jerárquico
│   └── verification.py         # verificador de invariantes (sin solapes, límites, kerf)
├── services/
│   ├── project_service.py
│   ├── plate_service.py
│   ├── inventory_service.py
│   ├── optimization_service.py
│   ├── report_service.py       # orquesta exportadores
│   ├── cost_service.py         # (preparado, stub)
│   └── furniture_generator.py  # (preparado) interfaz FurnitureGenerator + ManualGenerator
├── exporters/
│   ├── __init__.py             # load_exporters(): registro bajo demanda (PDF/SVG usan Qt)
│   ├── base.py                 # Protocol Exporter + ExportContext + registry
│   ├── tables.py               # tablas comunes (lista de cortes, secuencia, despiece)
│   ├── pdf_exporter.py         # QPdfWriter/QPainter, reutiliza SheetScene.render()
│   ├── csv_exporter.py         # ; + UTF-8 con BOM (Excel en español)
│   └── svg_exporter.py         # ejemplo mínimo: un SVG por placa
├── ui/
│   ├── main_window.py
│   ├── project_widget.py
│   ├── plate_widget.py
│   ├── pieces_widget.py
│   ├── parameters_widget.py    # "optimization_widget" del enunciado
│   ├── result_widget.py
│   ├── cutting_diagram_widget.py
│   ├── cut_list_widget.py
│   ├── offcuts_widget.py
│   ├── inventory_widget.py
│   ├── furniture_widget.py     # (preparado) dimensiones generales del mueble
│   ├── workers.py              # QThread/QRunnable para optimizar sin bloquear
│   ├── units_display.py        # formateo según unidad elegida
│   ├── tooltips.py             # textos de ayuda de parámetros y veta
│   └── theme.py                # paleta, QSS, colores por categoría
├── utils/
│   ├── units.py
│   ├── geometry.py
│   └── constants.py
└── tests/
    ├── conftest.py
    ├── test_units.py
    ├── test_geometry.py
    ├── test_kerf.py
    ├── test_orientation.py
    ├── test_optimizer.py
    ├── test_cutting_plan.py
    ├── test_offcuts.py
    ├── test_repositories.py
    ├── test_services.py
    ├── test_exporters.py
    └── test_demo_mesita.py
```

## 4. Flujo de una optimización

1. UI recoge proyecto, placa(s), parámetros → `OptimizationService.optimize(project_id, params)`.
   En la UI el caso de uso se parte en `prepare` (pasos 2–4, hilo principal), `compute` (5–7, hilo de trabajo, sin DB) y `finish` (8, hilo principal).
2. Servicio: carga entidades, **valida** (`validation.py`) → si hay errores bloqueantes, devuelve `ValidationReport` sin optimizar.
3. Expande `PieceSpec` → `PieceInstance` (cantidad → instancias numeradas).
4. Construye `Bins` disponibles: retazos en stock (si se pidió), placas de inventario, y placas "nuevas" del formato elegido (ilimitadas).
5. `Optimizer.run(instances, bins, params)` → prueba N estrategias × ordenamientos × semillas según nivel; cada candidato pasa por `verification.verify()`; elige el de menor `Score`.
6. `CuttingPlanner.plan(layout)` → secuencia de cortes guillotina por placa.
7. `OffcutDetector.classify(layout)` → retazos reutilizables / desperdicio.
8. Se persiste `OptimizationResult` (JSON + tablas) y se devuelve a la UI.

## 5. Decisiones de arquitectura (ADR)

### ADR-001 — PySide6 como UI
Qt ofrece `QGraphicsScene` (diagramas a escala con zoom), `QPdfWriter` (PDF sin dependencias extra) y licencia LGPL. **Aceptada.**

### ADR-002 — Representación numérica de las dimensiones
Problema: kerf = 3.2 mm; sumar floats (`0.1 + 0.2`) genera errores acumulados y comparaciones `<=` falsas.
Decisión: el dominio expone **mm** (`Decimal` en la frontera UI/DB, máximo 1 decimal), pero el núcleo geométrico trabaja con **enteros en décimas de milímetro** (`1830 mm → 18300`). `utils/units.py` provee `to_internal(mm) -> int` y `to_mm(int) -> Decimal`. Todas las comparaciones geométricas son enteras ⇒ exactas. Se rechaza entrada con más de 1 decimal (precisión de taller: 0,1 mm). **Aceptada.**

### ADR-003 — Layouts guillotinables por defecto
Una escuadradora solo hace cortes de borde a borde (guillotina). MaxRects produce layouts más densos pero a veces **no guillotinables**. Decisión: todo candidato se comprueba con `CuttingPlanner`; si no es guillotinable se descarta en modo "escuadradora" (por defecto) o se acepta en modo "CNC" (parámetro `cut_mode`). **Aceptada.**

### ADR-004 — Kerf como inflado de piezas
Ver [04-plan-de-corte-fisico.md](04-plan-de-corte-fisico.md#2-modelo-del-kerf). Cada pieza ocupa `w + kerf` × `h + kerf` y el área útil es `W − 2·margen + kerf`. Garantiza kerf entre piezas sin lógica especial en cada algoritmo. **Aceptada.**

### ADR-005 — SQLite con repositorios y migraciones por `user_version`
Sin ORM pesado (stdlib `sqlite3`). Los resultados se guardan también como JSON para reproducibilidad. **Aceptada.**

### ADR-006 — Optimización en hilo de trabajo
`QThreadPool` + señales; cancelable; el núcleo es puro y recibe un `CancellationToken`. **Aceptada.**

## 6. Puntos de extensión

| Extensión futura | Punto de enganche |
|------------------|-------------------|
| Generador de muebles | `services/furniture_generator.py` → `FurnitureGenerator.generate(dims, rules) -> list[PieceSpec]` |
| Nuevos algoritmos | `optimization/packing.py` → registrar en `STRATEGIES` |
| DXF / SVG / CNC (G-code) | `exporters/` → implementar `Exporter` y registrar |
| Costos | `models/costos.py` + `services/cost_service.py` |
| Proveedores / materiales | tablas `suppliers`, `materials` ya presentes en esquema v1 |
| Multi-material | el optimizador agrupa piezas por (material, espesor) y corre una optimización por grupo |
