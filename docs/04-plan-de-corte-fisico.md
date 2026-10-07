# 04 — Plan de corte físico

> **Optimización matemática** = dónde va cada pieza (layout).
> **Plan de corte físico** = qué cortes hace el operario, en qué orden y con qué medida, teniendo en cuenta que la sierra consume material.
> Son dos módulos separados: `optimization/packing.py` + `optimizer.py` vs `optimization/cutting.py` + `offcuts.py`.

## 1. Conceptos de taller

| Concepto | Definición | Parámetro |
|----------|-----------|-----------|
| **Kerf** | Ancho del material que elimina el disco en cada corte (dientes con traba). Típico 3,0–4,4 mm | `kerf` |
| **Margen / refilado** | Franja perimetral descartada porque los bordes de fábrica suelen venir golpeados o fuera de escuadra | `edge_margin` |
| **Separación extra** | Holgura adicional entre piezas (p. ej. para incisor/marcador o para repaso) | `extra_spacing` |
| **Veta** | Dirección de la fibra o del dibujo del laminado. Debe respetarse en frentes visibles | `grain` |
| **Tolerancia** | Precisión de la medida final: ±0,5 mm en escuadradora, ±0,1 mm en CNC. El sistema calcula exacto a 0,1 mm y la tolerancia es del proceso | informativo |
| **Corte guillotina** | Corte recto de borde a borde de la pieza/tira actual | — |
| **Tira** | Franja obtenida en el primer nivel de cortes | — |
| **Retazo** | Sobrante rectangular reutilizable | `min_offcut_*` |

## 2. Modelo del kerf

```
Placa W = 1830, margen m = 10, kerf k = 3.2
Área útil en espacio de packing: W_u = 1830 − 20 + 3.2 = 1813.2

Dos piezas de 500 de ancho en fila:
  pieza 1: x = 10            → ocupa [10, 510]
  kerf:                         [510, 513.2]
  pieza 2: x = 513.2         → ocupa [513.2, 1013.2]
  kerf:                         [1013.2, 1016.4]
  ...
  La última pieza termina como máximo en 1820 = W − m.  ✔
```

Invariantes verificados en `verification.py` (sobre coordenadas reales):

1. `x ≥ m`, `y ≥ m`, `x + w ≤ W − m`, `y + h ≤ H − m`.
2. Para cada par de piezas: separación horizontal o vertical `≥ k + extra_spacing` (no solo "no se solapan").
3. Dimensiones colocadas = dimensiones de la pieza (o intercambiadas si `rotated`), **exactas**.
4. Orientación ∈ orientaciones permitidas.

> El ejemplo del enunciado (`x = 10`, luego `x = 513`) es con kerf 3 mm; con 3,2 mm la segunda pieza va en 513,2. El sistema muestra 1 decimal.

## 3. Veta y orientación

- La placa tiene su propia veta (`PlateGrain`); en melamina con dibujo madera suele ir a lo largo del lado mayor.
- La pieza declara la veta respecto a **su alto** (VERTICAL) o **su ancho** (HORIZONTAL).
- El sistema rota la pieza solo si eso alinea su veta con la de la placa (tabla en [03 §3](03-algoritmo-de-optimizacion.md#3-orientaciones-permitidas-optimizationorientationpy)).
- En el diagrama, cada pieza muestra una flecha/rayado indicando la veta y un icono ⟲ si fue rotada.
- En la lista de cortes, columna **Rotación**: `No` / `Sí (90°)`.

## 4. Secuencia de cortes (`optimization/cutting.py`)

### 4.1 Árbol de cortes
Para layouts guillotinables se construye un árbol: cada nodo es una región rectangular; un corte la divide en dos. Las hojas son piezas o sobrantes.

### 4.2 Orden de ejecución (escuadradora)
1. **Refilado** de los 4 bordes (si `edge_margin > 0`): cortes 0a–0d.
2. **Nivel 1**: cortes a lo largo de la placa que separan tiras (p. ej. cortes transversales de 1830 mm).
3. **Nivel 2**: dentro de cada tira, cortes perpendiculares que separan piezas.
4. **Nivel 3+**: recortes finales.
5. Orden dentro de un nivel: de un extremo al otro (no saltar), priorizando sacar primero las tiras que contienen más piezas.

### 4.3 Salida
```
PLACA 1 — Melamina blanca 18 mm (1830 × 2820)
CORTE 1  [refilado]   horizontal  y = 10      longitud 1830 mm
...
CORTE 5  [nivel 1]    horizontal  y = 610     longitud 1830 mm   → tira A (600 mm)
CORTE 6  [nivel 2]    vertical    x = 410     longitud  600 mm   → Lateral 1 (400 × 600)
...
```
Cada `Cut` incluye: orden, nivel, orientación, posición absoluta, longitud, **medida a ajustar en el tope** (distancia desde el borde de referencia de la región), piezas resultantes.

### 4.4 Métricas
`cut_count`, `total_cut_length`, `cuts_by_level`, `kerf_area` (en `CutPlan`). El optimizador puntúa con el número y la longitud de cortes del mismo árbol (sin el refilado, que es igual en toda placa entera).

### 4.5 Modo CNC
Si el layout no es guillotinable (solo permitido en `CutMode.CNC`), no se genera secuencia de escuadradora; se genera la lista de contornos por pieza (base para G-code/DXF futuros).

### 4.6 Implementación (sprint 3)
- **Pasadas y niveles.** Los cortes paralelos de una misma región se agrupan en una pasada, aunque en el árbol de `guillotine.py` vengan anidados (p. ej. tiras + recorte de un sobrante del mismo lado). Cada cambio de orientación es un nivel más. El refilado es el nivel 0.
- **Refilado**: izquierda, derecha, arriba, abajo. El kerf cae dentro del margen: el corte izquierdo está en `x = margen − kerf`. Si el margen es más estrecho que el kerf, el corte se lleva solo el margen (`Cut.kerf` < kerf nominal).
- **Medida de tope** = distancia desde el borde actual de la región hasta el corte, es decir, el ancho de la franja que separa. Tras refilar un borde, el tope del opuesto es la medida útil (p. ej. 1810 mm).
- **Orden**: por niveles. Dentro de una región, de menor a mayor coordenada. Entre regiones del mismo nivel, primero la que tiene más piezas.
- **Nombres**: «Tira A, B…» en el nivel 1 y «Tira A.1, A.2…» dentro de ellas, por posición. Los retazos reutilizables se numeran `R<placa>.<n>`, el mayor primero.
- **Cada corte libera** la franja anterior; el último de la pasada, también la siguiente.
- **Partición exacta**: piezas + kerf + retazos + desperdicio (incluido el refilado) = área de la placa, en enteros. Lo comprueba un simulador de taller independiente que aplica los cortes uno a uno (`tests/helpers.py::simulate_cuts`).
- **CNC no guillotinable**: el árbol marca la zona sin líneas libres como bloque. Se informan los contornos de las piezas y los retazos de la parte que sí es separable. En ese caso no se calcula el kerf, así que el cuadre exacto de áreas solo se garantiza en escuadradora.

## 5. Retazos (`optimization/offcuts.py`)

1. Tras construir el árbol, las **hojas vacías** son sobrantes rectangulares (exactamente cortables, ya descontado el kerf).
2. Fusionar sobrantes adyacentes que formen un rectángulo cortable con un solo corte menos. Se prueba primero la fusión que da el rectángulo mayor. Se acepta si la placa, tratando los sobrantes como piezas, sigue siendo guillotinable sin más cortes.
3. Clasificar:
   - `REUSABLE` si `ancho ≥ min_offcut_width` **y** `alto ≥ min_offcut_height` **y** área ≥ `min_offcut_area_m2`. Ancho y alto se aceptan en cualquier orientación, porque el retazo se puede girar al guardarlo.
   - `WASTE` en caso contrario (incluye kerf y refilado).
4. La UI ofrece "Guardar retazos en stock" → `InventoryService.save_offcuts(result_id, labels)` → `OffcutRepository` con estado `IN_STOCK`. En el resultado guardado el retazo queda como `IN_STOCK` con el id del stock, así que no se puede guardar dos veces. Al usarlos en otra optimización pasan a `CONSUMED`.
5. Los retazos en stock se usan como bins (sin refilado si ya están escuadrados; parámetro por retazo).

## 6. Hoja de taller (resumen para el operario)
Generada en PDF/CSV: datos de placa, parámetros (kerf/margen), secuencia de cortes, tabla de piezas con etiqueta, retazos a guardar. Ver [sprint 6](sprints/sprint-06-exportacion-inventario-retazos.md).
