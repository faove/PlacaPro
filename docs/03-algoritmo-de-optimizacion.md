# 03 — Algoritmo de optimización

## 1. Planteamiento del problema

**2D rectangular bin packing con rotación restringida** (variante *2D-BPP* / *cutting stock* con piezas heterogéneas):

- Entrada: n piezas rectangulares (`w_i`, `h_i`, orientaciones permitidas), bins (placas) de `W × H`, kerf `k`, margen `m`.
- Salida: asignación pieza → (placa, x, y, rotada) sin solapes, dentro del área útil.
- Objetivo lexicográfico: **min placas** → **min desperdicio "disperso"** → **min cortes**.

Es NP-difícil; usamos heurísticas constructivas de calidad probada + búsqueda multi-arranque.

## 2. Transformación al espacio de empaquetado (kerf y margen)

Todo en unidades internas enteras (0,1 mm).

```
k' = kerf + extra_spacing
Área útil:     W_u = W − 2·m + k'      H_u = H − 2·m + k'
Pieza inflada: w' = w + k'             h' = h + k'
Coordenada real de la pieza = (x_packing + m, y_packing + m)
```

Justificación: entre dos piezas adyacentes siempre queda exactamente `k'`; la última pieza de una fila termina como máximo en `W − m` (el "kerf sobrante" cae dentro del margen de refilado). Ver demostración y ejemplos numéricos en [04-plan-de-corte-fisico.md](04-plan-de-corte-fisico.md).

Validaciones previas: `W_u > 0`, `H_u > 0`; cada pieza debe caber en al menos una orientación permitida (`w' ≤ W_u` y `h' ≤ H_u`, o rotada).

## 3. Orientaciones permitidas (`optimization/orientation.py`)

Función pura `allowed_orientations(piece, plate_grain, params) -> {0°} | {90°} | {0°, 90°}`:

| Placa | Veta pieza | Rotación pieza | Resultado |
|-------|-----------|----------------|-----------|
| cualquiera | NONE | permitida y global=Sí y no fija | {0°, 90°} |
| cualquiera | NONE | no permitida / fija / global=No | {0°} |
| ALONG_HEIGHT | VERTICAL | — | {0°} (veta de pieza ya alineada) |
| ALONG_HEIGHT | HORIZONTAL | — | {90°} (hay que girarla para alinear su veta) |
| ALONG_WIDTH | VERTICAL | — | {90°} |
| ALONG_WIDTH | HORIZONTAL | — | {0°} |
| NONE | VERTICAL/HORIZONTAL | — | {0°} (se respeta la orientación dibujada) |

La veta **siempre gana** sobre "rotación permitida". `fixed_orientation=True` fuerza {0°}.

## 4. Algoritmos de colocación (`optimization/packing.py`)

Interfaz común:
```python
class Packer(Protocol):
    def __init__(self, width: int, height: int): ...
    def find_position(self, w: int, h: int, orientations) -> Candidate | None
    def place(self, candidate) -> None
    def free_rects(self) -> list[Rect]
```

### 4.1 Guillotine (principal en modo escuadradora)
- Lista de rectángulos libres; al colocar, el libre se divide en dos con un corte de borde a borde.
- **Selección de rectángulo libre**: Best Area Fit (BAF), Best Short Side Fit (BSSF), Best Long Side Fit (BLSF).
- **Regla de división**: Shorter Leftover Axis (SLAS), Longer Leftover Axis (LLAS), Min Area (MINAS), Max Area (MAXAS), horizontal/vertical fijo.
- **Fusión de rectángulos libres** adyacentes (rect merge) tras cada colocación.
- Produce siempre layouts guillotinables y guarda el árbol de cortes ⇒ alimenta directamente al `CuttingPlanner`.

### 4.2 MaxRects (más denso; modo CNC o candidato verificado)
- Mantiene rectángulos libres maximales (pueden solaparse); al colocar se recortan todos los libres intersectados y se eliminan los contenidos en otros.
- Heurísticas: BSSF, BLSF, BAF, Bottom-Left (BL), Contact Point (CP).
- Tras empaquetar se verifica guillotinabilidad (ver §6); en modo `PANEL_SAW` se descarta si no lo es.

### 4.3 Tiras / niveles guiados por el taller (opcional, "rápida")
- Shelf/FFDH por tiras horizontales o verticales: muy fácil de cortar (2 etapas), menos denso. Sirve como baseline y fallback garantizado.

### 4.4 Multi-placa
- Estrategia *bin-by-bin* (llenar una placa al máximo antes de abrir otra) y *global best fit* (cada pieza va a la placa abierta donde mejor encaja, si no cabe se abre una nueva).
- Orden de bins: retazos en stock → placas de inventario → placas nuevas, cuando el usuario lo pide.

## 5. Búsqueda (`optimization/optimizer.py`)

### Ordenamientos de piezas
Área desc, lado mayor desc, perímetro desc, ancho desc, alto desc, diferencia de lados desc, y **perturbaciones aleatorias** (swap de vecinos, shuffle por bloques) con semilla.

### Niveles
| Nivel | Combinaciones | Extra |
|-------|---------------|-------|
| Rápida | ~3 ordenamientos × 2 heurísticas guillotina × shelf | — |
| Equilibrada | todos los ordenamientos × todas las heurísticas (Guillotine + MaxRects) | 50 perturbaciones aleatorias sobre el mejor |
| Máxima | ídem + búsqueda local | Ruin & Recreate / *late acceptance* sobre la última placa durante un presupuesto de tiempo (p. ej. 20 s); intento explícito de "vaciar la última placa" redistribuyendo sus piezas |

Cada candidato: `verification.verify(layout)` → si falla, se descarta y se registra (nunca debe pasar; es una red de seguridad). Cancelable por `CancellationToken`. Determinista por semilla.

### Cota inferior
`LB = ceil(Σ área_inflada / área_útil)`; si un candidato alcanza `LB` placas, en modo rápido/equilibrado se corta la búsqueda de "menos placas" y solo se mejora el score secundario.

## 6. Verificación de guillotinabilidad

Recursivo sobre una región: buscar una línea vertical u horizontal que no atraviese ninguna pieza (considerando el kerf como franja de corte) y divida las piezas en dos grupos no vacíos; recursión en ambas mitades. Si alguna región con ≥ 2 piezas no tiene línea ⇒ no guillotinable. Coste O(n² log n), aceptable para n < 500.

## 7. Función de puntuación (`optimization/scoring.py`)

El enunciado propone `placas × 1.000.000 + desperdicio + cortes × penalización`. **Problema detectado**: con un número fijo de placas, el desperdicio total es constante (área de placas − área de piezas), así que ese término no discrimina. Se usa un score **lexicográfico** (tupla comparada en orden):

```python
Score = (
    sheets_used,                    # 1. menos placas
    -last_sheet_free_concentration, # 2. última placa lo más vacía posible / piezas concentradas en las primeras
    -largest_reusable_offcut_area,  # 3. retazos grandes y aprovechables > muchos pedazos chicos
    unusable_waste_area,            # 4. desperdicio no aprovechable mínimo
    cut_count,                      # 5. menos cortes
    total_cut_length,               # 6. menos metros de corte
)
```

Equivalente escalar (para mostrar y comparar con la propuesta del cliente):
`score = placas × 10^12 + desperdicio_no_aprovechable_dmm² + cortes × P_CORTE` con `P_CORTE` configurable. Se documenta en el README la diferencia y la razón.

## 8. Complejidad y rendimiento

- Guillotine: O(n · F) por colocación (F = libres) ⇒ O(n²) por intento.
- MaxRects: O(n · F²) peor caso; F se mantiene pequeño con poda.
- n = 100, nivel equilibrado ≈ 300–600 intentos ⇒ objetivo < 5 s en Python puro. Si no se alcanza: cachear ordenamientos, `__slots__`, y como último recurso `multiprocessing` por estrategia.

## 9. Lo que el algoritmo NO hace en v1

- Piezas no rectangulares, cantos/tapacantos (se añade en roadmap: el canto descuenta medida).
- Optimización conjunta de varios materiales distintos en la misma placa (se agrupa por material+espesor y se optimiza por grupo).
- Garantía de óptimo global (heurístico; se informa la cota inferior al usuario).
