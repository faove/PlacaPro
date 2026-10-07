# Benchmarks del optimizador

Generado con `python scripts/benchmark.py --write` el 2026-10-07 (Python 3.12.15).

Placa 1830 × 2820 mm, kerf 3,2 mm, margen 10 mm, modo escuadradora. Instancias sintéticas de piezas de muebles (semilla = nº de piezas).

La *cota inferior* es ⌈Σ área inflada / área útil⌉. Solo considera áreas, así que con piezas grandes suele ser inalcanzable: llegar a ella demuestra el óptimo, pero no llegar no demuestra lo contrario.

| Piezas | Nivel | Cota inferior | Placas | Aprovechamiento | Intentos | Tiempo (s) | Verificado |
|---:|---|---:|---:|---:|---:|---:|---|
| 20 | Rápida | 2 | 2 | 69.9% | 10 | 0.01 | sí |
| 20 | Equilibrada | 2 | 2 | 69.9% | 192 | 0.15 | sí |
| 20 | Máxima | 2 | 2 | 69.9% | 282 | 0.22 | sí |
| 50 | Rápida | 4 | 4 | 77.6% | 10 | 0.02 | sí |
| 50 | Equilibrada | 4 | 4 | 77.6% | 192 | 0.38 | sí |
| 50 | Máxima | 4 | 4 | 77.6% | 394 | 0.81 | sí |
| 100 | Rápida | 8 | 8 | 87.5% | 10 | 0.06 | sí |
| 100 | Equilibrada | 8 | 8 | 87.5% | 192 | 0.87 | sí |
| 100 | Máxima | 8 | 8 | 87.5% | 1010 | 4.45 | sí |
| 200 | Rápida | 15 | 16 | 89.9% | 10 | 0.14 | sí |
| 200 | Equilibrada | 15 | 16 | 89.9% | 192 | 2.09 | sí |
| 200 | Máxima | 15 | 16 | 89.9% | 2110 | 25.01 | sí |
