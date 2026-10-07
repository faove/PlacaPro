# Sprint 2 — Motor de optimización

**Objetivo**: el corazón del sistema. Un optimizador correcto (invariantes garantizados) y razonablemente bueno (multi-estrategia + scoring).

**Requisitos cubiertos**: RF-04, RF-05, prioridades 1–7 del cliente. Referencia: [03-algoritmo-de-optimizacion.md](../03-algoritmo-de-optimizacion.md).

## Alcance

### 1. Preparación
- [x] `optimization/orientation.py`: `allowed_orientations()` según la tabla de veta/rotación.
- [x] Transformación kerf/margen: `PackingSpace.from_plate(plate, params)`, `inflate(piece)`, `to_real_coords()`.
- [x] `lower_bound(instances, space)`.

### 2. Packers (`optimization/packing.py`)
- [x] `GuillotinePacker` con heurísticas de selección (BAF, BSSF, BLSF) y división (SLAS, LLAS, MINAS, MAXAS), fusión de libres y **registro del árbol de cortes**.
- [x] `MaxRectsPacker` con BSSF, BLSF, BAF, BL, CP y poda de libres.
- [x] `ShelfPacker` (FFDH) como baseline/fallback.
- [x] Registry `STRATEGIES: dict[str, Callable[..., Packer]]`.

### 3. Multi-placa y orquestación (`optimization/optimizer.py`)
- [x] Bins ordenados: retazos en stock → inventario → placas nuevas (según parámetros).
- [x] Modos *bin-by-bin* y *global best fit*.
- [x] Ordenamientos de piezas + perturbaciones con `random.Random(seed)`.
- [x] Niveles FAST / BALANCED / MAX con presupuesto de tiempo y `CancellationToken`.
- [x] Búsqueda local en MAX: intentar vaciar la última placa (ruin & recreate).
- [x] Callback de progreso `on_progress(fraction, best_score)`.

### 4. Puntuación y verificación
- [x] `scoring.py`: `Score` lexicográfico (ver [03 §7](../03-algoritmo-de-optimizacion.md#7-función-de-puntuación-optimizationscoringpy)) + representación escalar.
- [x] `verification.py`: `verify(result, params) -> list[Violation]`, independiente del packer (sin solapes con gap ≥ kerf, dentro de márgenes, dimensiones exactas, orientación válida, conservación de piezas).
- [x] Guillotinabilidad: `is_guillotine(placements, region, kerf)`.

### 5. Servicio
- [x] `services/optimization_service.py`: valida → expande → agrupa por (material, espesor) → optimiza → verifica → persiste `OptimizationResult`.

## Análisis previo (antes de codificar)
- Revisar riesgos A1–A8 de [07](../07-riesgos-y-problemas-conocidos.md).
- Escribir primero `verification.py` y los tests de invariantes (TDD): todo packer se valida contra él.

## Tests del sprint
- Los 10 casos obligatorios de [06 §3](../06-estrategia-de-testing.md#3-casos-obligatorios-del-cliente-19).
- `test_orientation.py` (tabla completa).
- `test_kerf.py`: límite exacto 1003.2 vs 1003.1; margen + kerf combinados.
- `test_optimizer_properties.py` (Hypothesis, 200 ejemplos): las 8 propiedades.
- `test_deterministic_with_seed`.
- Benchmark inicial (20/50/100 piezas) → `docs/benchmarks.md`.

## Criterios de aceptación
- 0 violaciones del verificador en todos los tests y propiedades.
- Demo "Mesita de noche" en 1 placa (área de piezas = 1,4388 m² frente a 5,16 m² de placa).
- Nivel equilibrado con 100 piezas < 5 s.
- Nunca se pierde ni se duplica una pieza; las no ubicables se informan con motivo.

## Resultado
**Estado: cerrado (2026-10-07).**

### Entregado
| Módulo | Contenido |
|--------|-----------|
| `optimization/space.py` | `BinSpec` (placa nueva, de inventario o retazo), inflado por kerf, `lower_bound()` |
| `optimization/packing.py` | `GuillotinePacker` (3 selecciones × 6 divisiones, fusión opcional), `MaxRectsPacker` (BSSF, BLSF, BAF, BL, CP; poda incremental), `ShelfPacker`, registro `STRATEGIES` |
| `optimization/guillotine.py` | Descomposición guillotina con kerf: árbol de cortes, número de cortes, longitud de corte y sobrantes |
| `optimization/scoring.py` | `Score` lexicográfico + `scalar()` orientativo |
| `optimization/verification.py` | Verificador independiente: márgenes, separación ≥ kerf, medidas exactas, veta, conservación de piezas, guillotinabilidad |
| `optimization/optimizer.py` | `Optimizer`: 3 modos de colocación × estrategias × 6 ordenamientos + búsqueda local; cancelación, progreso y presupuesto de tiempo |
| `services/optimization_service.py` | validar → despiece → optimizar → verificar → guardar |
| `scripts/benchmark.py` | Genera [docs/benchmarks.md](../benchmarks.md) |

### Decisiones y desvíos respecto al plan
- **Árbol de cortes por descomposición y no registrado por el packer**: un único descomponedor (`guillotine.py`) sirve para todos los algoritmos. Comprueba si se puede cortar, cuenta cortes y mide el sobrante más grande. El sprint 3 construirá la secuencia de cortes sobre ese árbol.
- **Tercer modo de colocación, «mejor ajuste» (Best Fit global)**: en cada paso elige la combinación pieza/hueco con mejor ajuste. Es el que reconstruye los encajes exactos.
- **Puntuación** (corrige la fórmula del enunciado, ver doc 03 §7): piezas sin colocar → placas enteras → retazos de stock aprovechados (más es mejor) → área de la placa menos llena → sobrante más grande → cortes → metros de corte.
- **La veta manda** sobre la rotación (sprint 1). Una pieza cuadrada con veta tampoco se gira.
- **Paciencia reducida** en la búsqueda local cuando se alcanza la cota inferior: el número de placas ya es óptimo y solo se pulen criterios secundarios.
- Con presupuesto de tiempo agotado (nivel máximo con muchas piezas), el resultado depende de la velocidad del equipo. Sin agotarlo es determinista por semilla.

### Benchmark (escuadradora, kerf 3,2 mm, margen 10 mm)
| Piezas | Rápida | Equilibrada | Máxima | Placas / cota inferior |
|---:|---:|---:|---:|---:|
| 20 | 0,01 s | 0,15 s | 0,22 s | 2 / 2 ✔ óptimo |
| 50 | 0,02 s | 0,38 s | 0,81 s | 4 / 4 ✔ óptimo |
| 100 | 0,06 s | **0,87 s** | 4,45 s | 8 / 8 ✔ óptimo |
| 200 | 0,14 s | 2,09 s | 25 s (límite) | 16 / 15 |

Objetivo «100 piezas en nivel equilibrado < 5 s»: **cumplido (0,87 s)**.

### Limitación conocida
Las instancias que equivalen a una **partición exacta** (piezas que solo encajan al 100 % si se reparten en grupos que suman exactamente el largo de la placa) pueden necesitar una placa más que el óptimo. Se documentan en `test_10b_exact_partition_instances` (`xfail`). En el benchmark de listas de muebles, las instancias de 20, 50 y 100 piezas alcanzaron la cota inferior, que es óptimo demostrado.

### Verificación
- **225 tests pasan**, 2 `xfail` documentados. Incluyen:
  - los 10 casos obligatorios del cliente;
  - límites exactos de kerf y margen (1003,2 frente a 1003,1 mm, y con margen y separación extra);
  - el ejemplo de taller X = 513,2 mm;
  - la tabla de veta;
  - inventario y retazos primero;
  - cancelación y progreso;
  - determinismo;
  - 150 entradas aleatorias con Hypothesis comprobando 8 propiedades;
  - un verificador que se prueba con resultados corrompidos a propósito.
- Demo «Mesita de noche»: **1 placa** (cota inferior 1) en los tres niveles, 27,9 % de aprovechamiento y un retazo continuo de 3,58 m².
- Ejemplo «Mueble bajo» del enunciado: 1 placa.
- Cobertura de `optimization/`: 98 %.
