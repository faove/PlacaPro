# 00 — Visión y requisitos

## 1. Visión

Un carpintero o fabricante de muebles define una **placa** (ej. melamina blanca 1830 × 2820 × 18 mm), carga las **piezas** de un mueble y pulsa **OPTIMIZAR CORTES**. El sistema devuelve:

- cuántas placas se necesitan,
- dónde va cada pieza (coordenadas reales en mm),
- la secuencia de cortes ejecutable en una escuadradora,
- el desperdicio y los retazos reutilizables,
- un PDF/CSV listo para llevar al taller.

Es un sistema para **taller real**, no académico: el kerf, la veta y los márgenes son restricciones duras.

## 2. Actores

| Actor | Necesidad |
|-------|-----------|
| Carpintero / operario | Lista de cortes clara, diagrama por placa, secuencia de cortes |
| Diseñador / presupuestador | Proyectos, cantidades de material, (futuro) costos y precio |
| Encargado de stock | Inventario de placas y retazos |

## 3. Requisitos funcionales

### RF-01 Placas (formatos)
- Crear/editar/eliminar formatos: nombre, ancho, alto, espesor, material, color, proveedor, dirección de veta de la placa, (futuro) costo.
- Formatos precargados: 1830×2820, 2440×1220, 2750×1830, 2800×2070, 3000×2100 (18 mm).
- Lista de placas guardadas seleccionable.

### RF-02 Piezas
- Campos: nombre, cantidad, ancho, alto, espesor, material, rotación permitida, dirección de veta (vertical / horizontal / indiferente), orientación obligatoria, categoría (lateral, tapa, base, fondo, puerta, divisor, estante, otro) — la categoría define el color.
- Las cantidades se **expanden** a piezas individuales numeradas (`Lateral 1`, `Lateral 2`) antes de optimizar.

### RF-03 Proyectos / muebles
- Proyecto = contenedor (ej. "Mesita de noche") con uno o más muebles; cada mueble tiene piezas.
- Operaciones: Nuevo, Abrir, Guardar, Guardar como, Duplicar, Eliminar.
- Pipeline explícito (ver arquitectura): Descripción → Dimensiones → Despiece → Piezas → Optimizador → Placas → Plan de corte → Resultado.

### RF-04 Parámetros de corte
- Kerf (ancho de disco), ej. 3.2 mm.
- Margen exterior (refilado), ej. 10 mm.
- Separación adicional entre piezas (además del kerf), por defecto 0.
- Rotación global permitida Sí/No.
- Nivel de optimización: rápida / equilibrada / máxima.
- Usar primero placas del inventario y retazos: Sí/No.
- Tamaño mínimo de retazo reutilizable (ancho y alto mínimos, configurable).

### RF-05 Optimización
- 2D rectangular bin packing / cutting stock con múltiples estrategias (MaxRects, Guillotine, Best Fit, ordenamientos, rotaciones, intentos aleatorizados).
- Selección por función de puntuación jerárquica (placas ≫ desperdicio ≫ cortes).
- Respeta kerf, margen, veta, orientación, dimensiones máximas.

### RF-06 Resultados
- Resumen global: placas, área total, área utilizada, desperdicio (m²), aprovechamiento %, nº de piezas.
- Por placa: piezas, coordenadas, área usada/desperdiciada, %, retazos.
- Lista de cortes (tabla): Nº, Pieza, Ancho, Alto, Placa, X, Y, Rotación.
- Secuencia de cortes por placa (CORTE 1: 2820 mm, ...).

### RF-07 Visualización
- Diagrama real con `QGraphicsView`/`QGraphicsScene` a escala.
- Cada pieza: nombre + número, dimensiones, indicador de orientación/veta.
- Colores por categoría con leyenda; gris = desperdicio; trama distinta para retazo reutilizable.
- Zoom, pan, selección (sincronizada con la tabla).

### RF-08 Retazos
- Clasificación del sobrante: **retazo reutilizable** vs **desperdicio**.
- Sección "Retazos disponibles"; se pueden guardar al stock y usar en proyectos futuros.

### RF-09 Inventario
- Stock de placas por formato (cantidad disponible).
- Opción "Utilizar primero las placas existentes" y retazos en stock.

### RF-10 Exportación
- PDF: p.1 info del proyecto, p.2 resumen de materiales, p.3..n una placa por página con diagrama y tabla.
- CSV: lista de piezas y de cortes.
- Arquitectura de exportadores enchufables (CNC, DXF, SVG futuros).

### RF-11 Unidades
- Entrada y cálculos en mm; visualización conmutable mm / cm / m.

### RF-12 Validaciones
Pieza mayor que la placa, dimensiones ≤ 0, cantidad 0, espesor distinto al de la placa, kerf inválido, margen que anula el área útil, piezas no acomodables. Mensajes claros y localizados en la pieza/campo culpable.

### RF-13 Demo
Proyecto "Mesita de noche" precargado (placa 1830×2820×18; piezas 2×400×600, 1×564×400, 1×564×600, 2×282×600, 1×564×100) que se optimiza automáticamente al primer arranque.

## 4. Requisitos no funcionales

| ID | Requisito |
|----|-----------|
| RNF-01 | 100 % local, sin servicios externos obligatorios |
| RNF-02 | `python app.py` arranca la aplicación |
| RNF-03 | Arquitectura limpia por capas; dominio y optimizador **sin dependencia de Qt** |
| RNF-04 | Precisión: sin errores de coma flotante en dimensiones (ver ADR-002) |
| RNF-05 | Rendimiento: ≤ 1 s modo rápido, ≤ 5 s equilibrado, ≤ 30 s máximo para ~100 piezas; la UI no se bloquea (worker thread) |
| RNF-06 | Determinismo: misma entrada + misma semilla ⇒ mismo resultado |
| RNF-07 | Tests automáticos con pytest; invariantes geométricos verificados en cada resultado |
| RNF-08 | Extensible: nuevos algoritmos, exportadores, generadores de muebles y materiales sin tocar el núcleo |

## 5. Fuera de alcance de la v1 (preparado en arquitectura)

Generador automático de muebles por reglas, costos/precio de venta, exportación CNC/DXF/SVG, proveedores, multi-material en una misma corrida con placas mixtas avanzadas. Ver [08-roadmap-futuro.md](08-roadmap-futuro.md).

## 6. Trazabilidad requisito → sprint

| Requisito | Sprint |
|-----------|--------|
| RF-11, RNF-04 | 0 |
| RF-01, RF-02, RF-03 (persistencia), RF-09 (modelo) | 1 |
| RF-04, RF-05 | 2 |
| RF-06 (secuencia), RF-08 | 3 |
| RF-01..RF-04 (UI), RF-03 (operaciones) | 4 |
| RF-06, RF-07 | 5 |
| RF-08 (UI), RF-09, RF-10 | 6 |
| RF-12, RF-13, README | 7 |
