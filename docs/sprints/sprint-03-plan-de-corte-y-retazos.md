# Sprint 3 — Plan de corte físico y retazos

**Objetivo**: convertir el layout matemático en una **secuencia de cortes ejecutable** en escuadradora y clasificar el sobrante en retazos reutilizables o desperdicio.

**Requisitos cubiertos**: RF-06 (secuencia), RF-08 (lógica), §13, §14, §26. Referencia: [04-plan-de-corte-fisico.md](../04-plan-de-corte-fisico.md).

## Alcance

### 1. `optimization/cutting.py`
- [x] `CutTree`: nodos región / corte / pieza / sobrante.
- [x] Construcción del árbol (por descomposición para todos los packers, ver desvíos):
  - a partir del árbol registrado por `GuillotinePacker` (directo), y
  - por descomposición recursiva para layouts de MaxRects/Shelf (reutiliza `is_guillotine`).
- [x] `CuttingPlanner.plan(sheet_layout, params) -> CutPlan`:
  - cortes de refilado (si margen > 0),
  - niveles 1, 2, 3+ con orden de ejecución de [04 §4.2](../04-plan-de-corte-fisico.md#42-orden-de-ejecución-escuadradora),
  - posición absoluta, longitud, **medida de tope** relativa a la región y piezas resultantes por corte.
- [x] Modo CNC: si no es guillotinable, `CutPlan` con `mode=CNC` y contornos por pieza.
- [x] Métricas: `cut_count`, `total_cut_length`, cortes por nivel → integrar en `scoring.py`.

### 2. `optimization/offcuts.py`
- [x] Extraer hojas vacías del árbol como sobrantes rectangulares.
- [x] Fusión de sobrantes adyacentes cuando el resultado sigue siendo cortable.
- [x] Clasificación `REUSABLE` / `WASTE` según mínimos de ancho, alto y área.
- [x] Métricas por placa: área de retazos reutilizables, desperdicio no aprovechable.

### 3. Integración
- [x] `OptimizationService` añade `cut_plan` y `offcuts` a cada `SheetLayout`.
- [x] Persistencia en `result_json`.
- [x] `InventoryService.save_offcuts(result_id, offcut_ids)` → estado `IN_STOCK`.
- [x] Retazos en stock utilizables como bins (con flag `needs_trim`).

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
**Estado: cerrado (2026-10-07).**

### Entregado
| Módulo | Contenido |
|--------|-----------|
| `optimization/cutting.py` | `CutTree` / `CutNode` (corte, pieza, sobrante, refilado, bloque CNC), `CuttingPlanner` (`build`, `plan`, `plan_sheet`), `plan_result()` para todo un resultado y `format_plan()` con el texto para el operario |
| `optimization/offcuts.py` | `classify()` (reutilizable / desperdicio) y `merge_offcuts()` (fusión que conserva la guillotina) |
| `optimization/guillotine.py` | Opción `allow_blocks`: en CNC, las zonas no guillotinables quedan como bloque en lugar de invalidar todo el árbol |
| `models/plan_corte.py` | `Cut.kerf` (kerf efectivo) y `Cut.region`; `CutPlan.kerf_area`, `cuts_by_level` y `contours` (`PieceContour`) |
| `models/retazo.py`, `models/resultado.py` | `Offcut.label` (`R<placa>.<n>`); `SheetLayout.kerf_area`; los retazos `IN_STOCK` siguen contando como reutilizables |
| `services/optimization_service.py` | Tras verificar, añade plan y retazos a cada placa; se guarda todo en `result_json` |
| `services/inventory_service.py`, `database/repositories.py` | `save_offcuts(result_id, labels=None)` y `ResultRepository.update()` |

### Decisiones y desvíos respecto al plan
- **Un solo constructor del árbol.** Igual que en el sprint 2, no se usa un árbol propio de `GuillotinePacker`: el árbol se obtiene descomponiendo la placa, sea cual sea el packer. Los cortes paralelos anidados se unen en una **pasada**, y el nivel sube con cada cambio de orientación.
- **Refilado como nivel 0**: izquierda, derecha, arriba, abajo. El kerf cae dentro del margen. Las franjas de refilado se guardan como retazos `WASTE` con nota «Refilado», para que el cuadre de áreas sea una suma de objetos.
- **Medida de tope** = ancho de la franja que separa cada corte (distancia al borde actual de la región). El simulador de los tests la comprueba en cada corte.
- **Orden de ejecución**: por niveles (doc 04 §4.2). Entre regiones del mismo nivel, primero la que tiene más piezas. Los nombres de las tiras van por posición (A, B…, A.1…), no por orden de corte, para que se lean en el diagrama.
- **Fusión de sobrantes**: se tratan los sobrantes como piezas y se acepta una fusión si la placa sigue siendo guillotinable sin más cortes.
- **Clasificación tolerante a la orientación**: los mínimos de ancho y alto valen en las dos orientaciones.
- **Puntuación sin cambios.** Ya desempataba por número y longitud de cortes, calculados con el mismo árbol (el refilado es igual en toda placa entera). Se probó añadir «desperdicio no aprovechable» y se descartó: empeoraba un caso de relleno perfecto (ver doc 03 §7).
- **Retazos a stock sin duplicados**: al guardarlos, el resultado persistido los marca `IN_STOCK` con el id del stock. Repetir la llamada no los vuelve a guardar. Marcar como `CONSUMED` al usarlos queda para el sprint 6, al confirmar un plan.
- **CNC no guillotinable**: no hay secuencia de escuadradora. Se dan los contornos de las piezas y los retazos de la parte separable. En ese modo no se calcula el kerf, así que el cuadre exacto de áreas solo está garantizado en escuadradora.

### Demo «Mesita de noche» (kerf 3,2 mm, margen 10 mm)
```
PLACA 1 — Melamina blanca 18 mm (1830 × 2820)
CORTE 1   [refilado]  vertical    x = 6,8      longitud   2820 mm   tope 6,8 mm   → Refilado
CORTE 2   [refilado]  vertical    x = 1820     longitud   2820 mm   tope 1810 mm   → Refilado
CORTE 3   [refilado]  horizontal  y = 6,8      longitud   1810 mm   tope 6,8 mm   → Refilado
CORTE 4   [refilado]  horizontal  y = 2810     longitud   1810 mm   tope 2800 mm   → Refilado
CORTE 5   [nivel 1]   horizontal  y = 859,2    longitud   1810 mm   tope 849,2 mm   → Tira A (849,2 mm), Retazo R1.1 (1810 × 1947,6)
CORTE 6   [nivel 2]   vertical    x = 610      longitud  849,2 mm   tope 600 mm   → Tira A.1 (600 mm)
CORTE 7   [nivel 2]   vertical    x = 1213,2   longitud  849,2 mm   tope 600 mm   → Tira A.2 (600 mm)
CORTE 8   [nivel 2]   vertical    x = 1816,4   longitud  849,2 mm   tope 600 mm   → Tira A.3 (600 mm), Desperdicio (0,4 × 849,2)
CORTE 9   [nivel 3]   horizontal  y = 410      longitud    600 mm   tope 400 mm   → Lateral 1 (600 × 400)
…
CORTE 16  [nivel 4]   vertical    x = 1780,4   longitud    400 mm   tope 564 mm   → Tapa (564 × 400), Desperdicio (32,8 × 400)
```
16 cortes (4 de refilado + 1 / 3 / 6 / 2 por nivel). Un retazo reutilizable de 1810 × 1947,6 mm (3,53 m²).
Cuadre exacto en dmm²: piezas 143 880 000 + kerf 5 669 632 + retazos 352 515 600 + desperdicio 13 994 768 = **516 060 000** = 1830 × 2820 mm.

### Verificación
- **254 tests pasan**, 2 `xfail` del sprint 2. Nuevos: `test_cutting_plan.py` (13), `test_offcuts.py` (15) y una propiedad más en `test_optimizer_properties.py`. Cubren:
  - **simulador de taller independiente**: aplica la secuencia corte a corte y exige el mismo multiconjunto de piezas y sobrantes, kerf y tope correctos en cada corte, y el cuadre exacto de áreas;
  - 2 piezas en fila → 4 de refilado + 1 tira + 1 separación, con posiciones y topes;
  - margen más estrecho que el kerf, sin margen, y pieza que llena la placa;
  - molinete de 5 piezas → no guillotinable; en CNC → contornos y retazo exterior;
  - fusión de sobrantes con un corte menos;
  - clasificación en los límites (600×400 reutilizable, 100×20 desperdicio);
  - guardado en stock sin duplicar, y reuso como placa en la siguiente optimización.
- **Propiedad 9** (Hypothesis, 150 ejemplos en la suite; 2000 sin fallos en una corrida aparte): en escuadradora, todo resultado aleatorio da un plan que reconstruye las piezas. Esta propiedad encontró el caso A14 (separación extra < kerf; doc 07), ya corregido.
- Coste del planificador: 45 ms para 400 piezas (22 placas).
- Cobertura: `cutting.py` 99 %, `offcuts.py` 98 %, `optimization/` 98 %.
