# Sprint 4 — Interfaz base

**Objetivo**: aplicación utilizable de punta a punta para cargar datos y lanzar la optimización (aún con visualización mínima).

**Requisitos cubiertos**: RF-01..RF-04 (UI), RF-03 (operaciones de proyecto), RF-11 (selector de unidades), §3, §4, §21, §23, §27. Referencia: [05-interfaz-de-usuario.md](../05-interfaz-de-usuario.md).

## Alcance

### 1. Arranque (`app.py`)
- [ ] Crear `QApplication`, abrir/migrar DB (`~/.placapro/placapro.db` o `PLACAPRO_DB`), ejecutar `seed()`, construir servicios (inyección manual) y `MainWindow`.
- [ ] Manejador global de excepciones → diálogo + log en `~/.placapro/placapro.log`.

### 2. `ui/main_window.py`
- [ ] Layout de tres paneles con `QSplitter`; panel izquierdo como acordeón (PROYECTO, PLACA, PIEZAS, PARÁMETROS).
- [ ] Menú Archivo: Nuevo, Abrir (diálogo con lista de proyectos), Guardar, Guardar como, Duplicar, Eliminar (con confirmación).
- [ ] Menú Ver: unidades mm/cm/m.
- [ ] Indicador de cambios sin guardar (`*` en el título) y aviso al cerrar.
- [ ] `QSettings` para geometría y última unidad/proyecto.

### 3. Widgets
- [ ] `project_widget.py`: nombre, descripción, mueble(s) (agregar/renombrar/eliminar), dimensiones generales opcionales.
- [ ] `plate_widget.py`: formulario + **Guardar placa** + lista de placas guardadas + stock.
- [ ] `pieces_widget.py`: `QAbstractTableModel` editable con delegados (spinbox decimal, combo de categoría y veta, checkboxes); agregar/duplicar/eliminar/reordenar; validación en línea.
- [ ] `parameters_widget.py`: kerf, margen, separación, rotación global, nivel, modo, usar stock/retazos, mínimos de retazo.
- [ ] `units_display.py`: conversión de presentación y entrada.
- [ ] `theme.py`: QSS base y paleta de categorías.

### 4. Ejecución de la optimización
- [ ] `ui/workers.py`: `OptimizationWorker(QRunnable)` con señales `progress`, `finished`, `failed`, `cancelled`.
- [ ] Botón grande **OPTIMIZAR CORTES** + barra de progreso + Cancelar.
- [ ] Panel de validación: lista de `ValidationIssue` clicable (selecciona la fila/campo).
- [ ] Resultado provisional: resumen en texto en el panel derecho.

## Tests del sprint
- `test_ui_smoke.py` (pytest-qt, offscreen): la ventana abre; se carga la demo; editar una pieza marca "sin guardar"; pulsar optimizar emite `finished` con un resultado.
- `test_units_display.py`: introducir "183" en cm guarda 1830 mm.
- `test_pieces_model.py`: edición, validación de celdas, agregar/eliminar.

## Criterios de aceptación
- `python app.py` abre la app con la demo cargada.
- El flujo crear proyecto → placa → piezas → parámetros → optimizar funciona sin congelar la UI.
- Nuevo / Abrir / Guardar / Guardar como / Duplicar / Eliminar funcionan contra SQLite.

## Resultado
_(completar al cerrar el sprint)_
