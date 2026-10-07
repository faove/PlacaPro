# Sprint 5 — Visualización y resultados

**Objetivo**: diagrama real a escala de cada placa, resumen de resultados, lista y secuencia de cortes, todo sincronizado.

**Requisitos cubiertos**: RF-06, RF-07, §9, §10, §11, §12, §13 (UI). Referencia: [05 §3–4](../05-interfaz-de-usuario.md#3-diagrama-de-placa-qgraphicsscene).

## Alcance

### 1. `ui/cutting_diagram_widget.py`
- [ ] `SheetScene(QGraphicsScene)` construida **solo** desde `SheetLayout` (1 unidad de escena = 1 mm).
- [ ] Ítems: placa, franja de margen, `PieceItem` (color por categoría, etiqueta "Lateral 1", "400 × 600", ⟲ si rotada, flecha de veta, tooltip con X/Y exactos), retazo reutilizable (rayado + etiqueta), desperdicio (gris).
- [ ] Capa opcional de líneas de corte numeradas según `CutPlan`; capa opcional de cotas.
- [ ] `SheetView(QGraphicsView)`: zoom con rueda, pan, "ajustar a ventana", antialiasing; texto legible en cualquier zoom.
- [ ] Pestañas: una por placa con título "Placa n — xx,x %".
- [ ] Leyenda generada desde `theme.CATEGORY_COLORS` (solo categorías presentes + retazo + desperdicio).

### 2. `ui/result_widget.py`
- [ ] Tarjetas KPI: Placas necesarias, Área total, Área utilizada, Desperdicio, Aprovechamiento %, Nº de piezas, (cota inferior, tiempo, estrategia).
- [ ] Tabla por placa: origen (nueva/inventario/retazo), piezas, % aprovechamiento, área usada, desperdicio, retazos.
- [ ] Aviso destacado si hay piezas no ubicadas.

### 3. `ui/cut_list_widget.py`
- [ ] Pestaña **Lista de cortes**: Nº, Pieza, Ancho, Alto, Placa, X, Y, Rotación (ordenable, filtrable por placa).
- [ ] Pestaña **Secuencia**: CORTE n, nivel, orientación, medida de tope, longitud, piezas resultantes.
- [ ] Sincronización bidireccional: seleccionar fila ⇄ resaltar pieza o corte en el diagrama (cambia de pestaña de placa si hace falta).

### 4. Persistencia del último resultado
- [ ] Al abrir un proyecto se muestra su último `OptimizationResult` (si los datos no cambiaron; si cambiaron, banner "Resultado desactualizado").

## Tests del sprint
- `test_diagram.py`: el número de `PieceItem` = colocaciones; el `rect()` de cada ítem coincide con `Placement` (x, y, w, h) exactos.
- `test_result_widget.py`: los KPI coinciden con las métricas del resultado.
- Selección sincronizada (pytest-qt).

## Criterios de aceptación
- La demo muestra su(s) placa(s) con piezas a escala correcta, colores por categoría y leyenda.
- Ningún rectángulo del diagrama se dibuja sin un `Placement` u `Offcut` detrás.
- Las unidades elegidas se reflejan en todas las tablas y etiquetas.

## Resultado
_(completar al cerrar el sprint; incluir captura en `docs/img/`)_
