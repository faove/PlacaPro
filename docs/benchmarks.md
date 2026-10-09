# Benchmarks del optimizador

Generado con `python scripts/benchmark.py --write` el 2026-10-09 (Python 3.12.15).

Placa 1830 × 2820 mm, kerf 3,2 mm, margen 10 mm, modo escuadradora. Instancias sintéticas de piezas de muebles (semilla = nº de piezas).

La *cota inferior* es ⌈Σ área inflada / área útil⌉. Solo considera áreas, así que con piezas grandes suele ser inalcanzable: llegar a ella demuestra el óptimo, pero no llegar no demuestra lo contrario.

| Piezas | Nivel | Cota inferior | Placas | Aprovechamiento | Intentos | Tiempo (s) | Verificado |
|---:|---|---:|---:|---:|---:|---:|---|
| 20 | Rápida | 2 | 2 | 69.9% | 10 | 0.01 | sí |
| 20 | Equilibrada | 2 | 2 | 69.9% | 192 | 0.15 | sí |
| 20 | Máxima | 2 | 2 | 69.9% | 282 | 0.22 | sí |
| 50 | Rápida | 4 | 4 | 77.6% | 10 | 0.02 | sí |
| 50 | Equilibrada | 4 | 4 | 77.6% | 192 | 0.35 | sí |
| 50 | Máxima | 4 | 4 | 77.6% | 394 | 0.79 | sí |
| 100 | Rápida | 8 | 8 | 87.5% | 10 | 0.05 | sí |
| 100 | Equilibrada | 8 | 8 | 87.5% | 192 | 0.87 | sí |
| 100 | Máxima | 8 | 8 | 87.5% | 1010 | 4.36 | sí |
| 200 | Rápida | 15 | 16 | 89.9% | 10 | 0.14 | sí |
| 200 | Equilibrada | 15 | 16 | 89.9% | 192 | 1.94 | sí |
| 200 | Máxima | 15 | 16 | 89.9% | 2402 | 25.01 | sí |

## Interfaz con 200 piezas (sprint 7)

Medido a mano con la ventana real (plataforma `offscreen`) y la instancia de 200 piezas de la tabla, nivel Equilibrada. Se cuenta cada cuánto llega a ejecutarse un temporizador de 16 ms del hilo de la interfaz mientras el optimizador corre en segundo plano.

| Situación | Mayor pausa de la UI |
|---|---:|
| Intervalo del GIL por defecto (5 ms) | ≈ 2 000 ms (ventana congelada toda la optimización) |
| `sys.setswitchinterval(0.001)` | ≈ 330 ms (solo al arrancar) |
| `sys.setswitchinterval(0.0005)` — **valor adoptado** | ≈ 170 ms al arrancar, < 50 ms durante el cálculo |

La causa era la contención del GIL: cada llamada de Qt a código Python (pintar la tabla de piezas, `data()` de los modelos) esperaba hasta 5 ms a que el hilo del optimizador lo soltara, y un repintado hace cientos de esas llamadas. El tiempo del optimizador no cambia de forma medible (2,10 s → 2,14 s). `app.py` fija el intervalo al arrancar (`ui/workers.py: GIL_SWITCH_INTERVAL_S`), y los avisos de progreso se limitan a uno cada 50 ms.

Otros tiempos con esa instancia (16 placas):

| Operación | Tiempo |
|---|---:|
| Cancelar (desde que se pulsa hasta que el optimizador se detiene) | 5–10 ms |
| Mostrar el resultado (diagrama + lista de cortes + secuencia) | ≈ 190 ms |
| Primera vista del diagrama de una placa | ≈ 280 ms (luego < 10 ms) |
