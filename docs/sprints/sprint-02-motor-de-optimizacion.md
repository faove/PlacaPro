# Sprint 2 — Motor de optimización

**Objetivo**: el corazón del sistema. Un optimizador correcto (invariantes garantizados) y razonablemente bueno (multi-estrategia + scoring).

**Requisitos cubiertos**: RF-04, RF-05, prioridades 1–7 del cliente. Referencia: [03-algoritmo-de-optimizacion.md](../03-algoritmo-de-optimizacion.md).

## Alcance

### 1. Preparación
- [ ] `optimization/orientation.py`: `allowed_orientations()` según la tabla de veta/rotación.
- [ ] Transformación kerf/margen: `PackingSpace.from_plate(plate, params)`, `inflate(piece)`, `to_real_coords()`.
- [ ] `lower_bound(instances, space)`.

### 2. Packers (`optimization/packing.py`)
- [ ] `GuillotinePacker` con heurísticas de selección (BAF, BSSF, BLSF) y división (SLAS, LLAS, MINAS, MAXAS), fusión de libres y **registro del árbol de cortes**.
- [ ] `MaxRectsPacker` con BSSF, BLSF, BAF, BL, CP y poda de libres.
- [ ] `ShelfPacker` (FFDH) como baseline/fallback.
- [ ] Registry `STRATEGIES: dict[str, Callable[..., Packer]]`.

### 3. Multi-placa y orquestación (`optimization/optimizer.py`)
- [ ] Bins ordenados: retazos en stock → inventario → placas nuevas (según parámetros).
- [ ] Modos *bin-by-bin* y *global best fit*.
- [ ] Ordenamientos de piezas + perturbaciones con `random.Random(seed)`.
- [ ] Niveles FAST / BALANCED / MAX con presupuesto de tiempo y `CancellationToken`.
- [ ] Búsqueda local en MAX: intentar vaciar la última placa (ruin & recreate).
- [ ] Callback de progreso `on_progress(fraction, best_score)`.

### 4. Puntuación y verificación
- [ ] `scoring.py`: `Score` lexicográfico (ver [03 §7](../03-algoritmo-de-optimizacion.md#7-función-de-puntuación-optimizationscoringpy)) + representación escalar.
- [ ] `verification.py`: `verify(result, params) -> list[Violation]`, independiente del packer (sin solapes con gap ≥ kerf, dentro de márgenes, dimensiones exactas, orientación válida, conservación de piezas).
- [ ] Guillotinabilidad: `is_guillotine(placements, region, kerf)`.

### 5. Servicio
- [ ] `services/optimization_service.py`: valida → expande → agrupa por (material, espesor) → optimiza → verifica → persiste `OptimizationResult`.

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
_(completar al cerrar el sprint: estrategia ganadora típica, métricas del benchmark)_
