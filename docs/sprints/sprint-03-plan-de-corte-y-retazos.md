# Sprint 3 — Plan de corte físico y retazos

**Objetivo**: convertir el layout matemático en una **secuencia de cortes ejecutable** en escuadradora y clasificar el sobrante en retazos reutilizables o desperdicio.

**Requisitos cubiertos**: RF-06 (secuencia), RF-08 (lógica), §13, §14, §26. Referencia: [04-plan-de-corte-fisico.md](../04-plan-de-corte-fisico.md).

## Alcance

### 1. `optimization/cutting.py`
- [ ] `CutTree`: nodos región / corte / pieza / sobrante.
- [ ] Construcción del árbol:
  - a partir del árbol registrado por `GuillotinePacker` (directo), y
  - por descomposición recursiva para layouts de MaxRects/Shelf (reutiliza `is_guillotine`).
- [ ] `CuttingPlanner.plan(sheet_layout, params) -> CutPlan`:
  - cortes de refilado (si margen > 0),
  - niveles 1, 2, 3+ con orden de ejecución de [04 §4.2](../04-plan-de-corte-fisico.md#42-orden-de-ejecución-escuadradora),
  - posición absoluta, longitud, **medida de tope** relativa a la región y piezas resultantes por corte.
- [ ] Modo CNC: si no es guillotinable, `CutPlan` con `mode=CNC` y contornos por pieza.
- [ ] Métricas: `cut_count`, `total_cut_length`, cortes por nivel → integrar en `scoring.py`.

### 2. `optimization/offcuts.py`
- [ ] Extraer hojas vacías del árbol como sobrantes rectangulares.
- [ ] Fusión de sobrantes adyacentes cuando el resultado sigue siendo cortable.
- [ ] Clasificación `REUSABLE` / `WASTE` según mínimos de ancho, alto y área.
- [ ] Métricas por placa: área de retazos reutilizables, desperdicio no aprovechable.

### 3. Integración
- [ ] `OptimizationService` añade `cut_plan` y `offcuts` a cada `SheetLayout`.
- [ ] Persistencia en `result_json`.
- [ ] `InventoryService.save_offcuts(result_id, offcut_ids)` → estado `IN_STOCK`.
- [ ] Retazos en stock utilizables como bins (con flag `needs_trim`).

## Tests del sprint
- `test_cutting_plan.py`:
  - **reconstrucción**: aplicar la secuencia de cortes a la placa (simulador) produce exactamente las piezas del layout, con el kerf restado en cada corte;
  - 2 piezas en una fila → refilado + 1 corte de tira + 1 corte de separación;
  - layout no guillotinable conocido (molinete / *pinwheel* de 5 piezas) → detectado.
- `test_offcuts.py`: retazo 600×400 → reutilizable; 100×20 → desperdicio; suma de áreas = área de placa.
- Propiedad: en `PANEL_SAW`, todos los resultados aleatorios generan un plan que reconstruye las piezas.

## Criterios de aceptación
- Para la demo "Mesita de noche" se genera una secuencia legible tipo "CORTE 1: 1830 mm …".
- `piezas + kerf + retazos + desperdicio = área de la placa` (exacto en enteros).
- El scoring desempata por número de cortes.

## Resultado
_(completar al cerrar el sprint)_
