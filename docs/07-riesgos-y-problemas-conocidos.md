# 07 — Riesgos y problemas analizados antes de implementar

## A. Algoritmo

| # | Problema | Impacto | Mitigación |
|---|----------|---------|-----------|
| A1 | **Errores de coma flotante** con kerf decimal (3.2) | Piezas que "caben" por 0.0000001 o superposiciones fantasma | Enteros en décimas de mm (ADR-002); rechazo de >1 decimal |
| A2 | **Kerf mal modelado**: añadirlo solo "entre" piezas complica cada heurística | Solapes físicos | Inflado uniforme `w+k`, área útil `W−2m+k` (ADR-004) + verificador independiente |
| A3 | **MaxRects produce layouts no guillotinables** | Imposible de cortar en escuadradora | Verificación de guillotinabilidad; Guillotine como estrategia principal (ADR-003) |
| A4 | **Score propuesto no discrimina desperdicio** (es constante con nº de placas fijo) | Selección arbitraria entre candidatos | Score lexicográfico: placas → concentración en última placa → retazo máximo → desperdicio inutilizable → cortes |
| A5 | **Ambigüedad de la veta**: "veta vertical" ¿respecto a la pieza o a la placa? | Puertas con veta cruzada (defecto visible) | Veta de pieza relativa a su alto; placa con veta propia; tabla de orientaciones; flecha de veta en diagrama |
| A6 | **Pieza mayor que la placa solo en una orientación** | Falsos errores o falsos OK | Validación usa orientaciones permitidas reales |
| A7 | **Explosión combinatoria** en nivel máximo | UI congelada / tiempos largos | Presupuesto de tiempo, hilo de trabajo, cancelación, cota inferior para cortar búsqueda |
| A8 | **No determinismo** por `random`/orden de dicts | Resultados distintos y tests frágiles | `random.Random(seed)` inyectado; ordenamientos estables con desempate por id |
| A9 | **Piezas de distinto espesor/material mezcladas** | Pieza de 15 mm puesta en placa de 18 mm | Validación + agrupación por (material, espesor) |
| A10 | **Retazos muy finos** contados como reutilizables | Stock lleno de tiras inútiles | Mínimos por ancho, alto y área configurables |
| A11 | **Margen vs retazo de stock**: un retazo ya escuadrado no necesita refilado | Pérdida innecesaria | Flag `needs_trim` por bin |
| A12 | **Optimalidad**: el usuario puede esperar el óptimo | Desconfianza | Mostrar cota inferior y "óptimo garantizado" solo cuando placas = LB |

## B. Entorno y tecnología

| # | Problema | Mitigación |
|---|----------|-----------|
| B1 | El sistema tiene **Python 3.8.10**; PySide6 recientes requieren ≥ 3.9 — **resuelto en sprint 0: Python 3.12 vía `uv`** | Usar Python **3.11/3.12** en un `venv` (pyenv o paquete del sistema). Documentar en README. Si no es posible: fijar `PySide6<6.6` compatible con 3.8 (no recomendado, 3.8 está fuera de soporte) |
| B2 | Dependencias gráficas de Qt en Linux (xcb) | Documentar `libxcb-cursor0` y similares; tests con `QT_QPA_PLATFORM=offscreen` |
| B3 | Generación PDF | Preferir `QPdfWriter` (sin dependencias); `reportlab` como alternativa si se necesitan tablas complejas |
| B4 | Ruta de la base de datos y permisos | `~/.placapro/` + variable `PLACAPRO_DB` |

## C. Producto

| # | Riesgo | Mitigación |
|---|--------|-----------|
| C1 | Alcance enorme para una v1 | Sprints con entregable funcional en cada uno; lo "preparado" son interfaces + tablas, sin UI |
| C2 | Interfaz compleja para un usuario de taller | Flujo lineal de 9 pasos, demo precargada, validaciones en línea |
| C3 | Discrepancia taller ↔ software (medidas de tope) | Secuencia de cortes con "medida a ajustar en el tope" y prueba con un caso real cortado |
