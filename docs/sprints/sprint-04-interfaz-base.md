# Sprint 4 — Interfaz base

**Objetivo**: aplicación utilizable de punta a punta para cargar datos y lanzar la optimización (aún con visualización mínima).

**Requisitos cubiertos**: RF-01..RF-04 (UI), RF-03 (operaciones de proyecto), RF-11 (selector de unidades), §3, §4, §21, §23, §27. Referencia: [05-interfaz-de-usuario.md](../05-interfaz-de-usuario.md).

## Alcance

### 1. Arranque (`app.py`)
- [x] Crear `QApplication`, abrir/migrar DB (`~/.placapro/placapro.db` o `PLACAPRO_DB`), ejecutar `seed()`, construir servicios (inyección manual) y `MainWindow`.
- [x] Manejador global de excepciones → diálogo + log en `~/.placapro/placapro.log`.

### 2. `ui/main_window.py`
- [x] Layout de tres paneles con `QSplitter`; panel izquierdo como acordeón (PROYECTO, PLACA, PIEZAS, PARÁMETROS).
- [x] Menú Archivo: Nuevo, Abrir (diálogo con lista de proyectos), Guardar, Guardar como, Duplicar, Eliminar (con confirmación).
- [x] Menú Ver: unidades mm/cm/m.
- [x] Indicador de cambios sin guardar (`*` en el título) y aviso al cerrar.
- [x] `QSettings` para geometría y última unidad/proyecto.

### 3. Widgets
- [x] `project_widget.py`: nombre, descripción, mueble(s) (agregar/renombrar/eliminar), dimensiones generales opcionales.
- [x] `plate_widget.py`: formulario + **Guardar placa** + lista de placas guardadas + stock.
- [x] `pieces_widget.py`: `QAbstractTableModel` editable con delegados (spinbox decimal, combo de categoría y veta, checkboxes); agregar/duplicar/eliminar/reordenar; validación en línea.
- [x] `parameters_widget.py`: kerf, margen, separación, rotación global, nivel, modo, usar stock/retazos, mínimos de retazo.
- [x] `units_display.py`: conversión de presentación y entrada.
- [x] `theme.py`: QSS base y paleta de categorías.

### 4. Ejecución de la optimización
- [x] `ui/workers.py`: `OptimizationWorker(QRunnable)` con señales `progress`, `finished`, `failed`, `cancelled`.
- [x] Botón grande **OPTIMIZAR CORTES** + barra de progreso + Cancelar.
- [x] Panel de validación: lista de `ValidationIssue` clicable (selecciona la fila/campo).
- [x] Resultado provisional: resumen en texto en el panel derecho.

## Tests del sprint
- `test_ui_smoke.py` (pytest-qt, offscreen): la ventana abre; se carga la demo; editar una pieza marca "sin guardar"; pulsar optimizar emite `finished` con un resultado.
- `test_units_display.py`: introducir "183" en cm guarda 1830 mm.
- `test_pieces_model.py`: edición, validación de celdas, agregar/eliminar.

## Criterios de aceptación
- `python app.py` abre la app con la demo cargada.
- El flujo crear proyecto → placa → piezas → parámetros → optimizar funciona sin congelar la UI.
- Nuevo / Abrir / Guardar / Guardar como / Duplicar / Eliminar funcionan contra SQLite.

## Resultado
**Estado: cerrado (2026-10-08).**

### Entregado
| Módulo | Contenido |
|--------|-----------|
| `app.py` | Log en `~/.placapro/placapro.log`, `sys.excepthook` → log + diálogo con el detalle, tema, DB por defecto (o `PLACAPRO_DB`) migrada + `seed()`, `create_main_window(db, settings, time_budget_s)` |
| `services/app_services.py` | `AppServices.from_db(db)`: contenedor de servicios (inyección manual) |
| `services/optimization_service.py` | El caso de uso se parte en `prepare` (validar + petición, usa la DB) → `compute` (puro: optimizar, verificar, planificar) → `finish` (avisos + guardar). `optimize()` sigue componiendo los tres |
| `ui/main_window.py` | Tres paneles con `QSplitter`; acordeón PROYECTO / PLACA / PIEZAS / PARÁMETROS; menús Archivo y Ver ▸ Unidades; `[*]` en el título y aviso al cerrar/abrir/nuevo; `QSettings` (geometría, splitter, unidad, último proyecto); validación en vivo (diferida 250 ms) |
| `ui/project_widget.py` | Nombre, descripción, muebles (agregar / renombrar en línea / eliminar) y dimensiones generales opcionales |
| `ui/plate_widget.py` | Lista de placas guardadas con stock; formulario; **Guardar placa** (crea o actualiza + stock); Nueva / Duplicar / Eliminar |
| `ui/pieces_widget.py` | `PiecesTableModel` + `PiecesDelegate`; selector de mueble; Agregar / Duplicar / Eliminar / Subir / Bajar; celdas en rojo con tooltip |
| `ui/parameters_widget.py` | Kerf, margen, separación, rotación, nivel, máquina, stock/retazos, mínimos de retazo (área en m²) |
| `ui/units_display.py` | `UnitsDisplay` (unidad compartida + señal) y `LengthEdit` (entrada exacta con `Decimal`) |
| `ui/theme.py` | Colores de categoría (fuente única), contraste automático del texto, QSS y paleta oscura básica |
| `ui/workers.py` | `OptimizationWorker(QRunnable)` con `progress` / `finished` / `failed` / `cancelled` |
| `ui/validation_panel.py`, `ui/result_widget.py`, `ui/open_project_dialog.py` | Lista clicable de `ValidationIssue`; resumen provisional en texto; diálogo Abrir |

### Decisiones y desvíos respecto al plan
- **SQLite fuera del hilo de trabajo.** La conexión `sqlite3` solo vale en el hilo que la creó, así que el worker ejecuta únicamente `OptimizationService.compute` (sin DB). Validar y guardar el resultado ocurren en el hilo principal (`prepare` / `finish`). Hay un test que corre `compute` en otro hilo.
- **Longitudes como texto, no `QDoubleSpinBox`.** El spinbox decimal de Qt trabaja con `float`, y ADR-002 lo prohíbe para longitudes. Los campos y las celdas interpretan el texto con `Decimal` en la unidad visible (coma o punto). Rechazan más precisión que 0,1 mm, conservan el último valor válido y marcan el error en rojo con el motivo.
- **Cancelar descarta la solución parcial.** El optimizador devuelve la mejor solución hallada hasta el momento, pero si el usuario canceló, el worker emite `cancelled` y no se muestra.
- **Validación en vivo.** El panel no espera a OPTIMIZAR: se recalcula 250 ms después de cada cambio. Tras optimizar se añaden los avisos de piezas no ubicadas. Clic en un mensaje → pieza (mueble + fila + columna), parámetro, placa o nombre del proyecto.
- **Piezas nuevas con medidas 0** y el espesor de la placa: la celda queda en rojo hasta que se completa, en lugar de inventar medidas.
- **Duplicar** pide guardar antes y abre la copia guardada. Si el proyecto nunca se guardó, equivale a «Guardar como … (copia)».
- **El resultado solo se guarda si el proyecto está guardado** (tiene id). Al abrir un proyecto se muestra su último resultado.
- **Categoría Zócalo**: no figuraba en la paleta del doc 05; se le asignó `#A1887F` (marrón grisáceo).

### Verificación
- **290 tests pasan** (2 `xfail` del sprint 2). Nuevos: `test_ui_smoke.py` (12), `test_pieces_model.py` (7), `test_units_display.py` (13 con parametrizados), `test_app.py` (3) y un test de hilos en `test_optimization_service.py`. Cubren:
  - la ventana abre con la demo; editar una pieza marca `[*]` y guardar lo limpia;
  - OPTIMIZAR emite `finished` con 7 piezas y el resultado queda persistido; cancelación del worker y desde la ventana;
  - errores de validación bloquean y el clic lleva a la celda; parámetro inválido → página PARÁMETROS;
  - Nuevo / Guardar / Guardar como / Duplicar / Eliminar / Abrir contra SQLite, incluido «Cancelar» y «Descartar» del aviso de cambios;
  - placa: seleccionar, guardar con stock, error de nombre vacío, eliminar → proyecto sin placa;
  - «183» en cm guarda 1830 mm; cambio de unidad en tabla, campos y barra de estado; persistencia de unidad y último proyecto en `QSettings`;
  - manejador global: registra el traceback y muestra el diálogo.
- Cobertura de `ui/`: 89 % en promedio (`units_display` y `validation_panel` 100 %, `main_window` 90 %).
- `python app.py` (offscreen, HOME temporal) crea `~/.placapro/placapro.db` y el log y abre la demo.
