# 05 — Interfaz de usuario

## 1. Layout principal (`ui/main_window.py`)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Menú: Archivo (Nuevo, Abrir, Guardar, Guardar como, Duplicar, Eliminar, Exportar ▸)  │
│       Ver (Unidades: mm/cm/m, Zoom)   Datos (Placas, Inventario, Retazos)   Ayuda    │
├───────────────────────┬──────────────────────────────────────┬───────────────────────┤
│ PANEL IZQUIERDO       │ PANEL CENTRAL                        │ PANEL DERECHO         │
│ (QToolBox / acordeón) │                                      │                       │
│ ▸ PROYECTO            │  [Placa 1] [Placa 2] [Placa 3] (tabs)│ RESULTADO             │
│ ▸ PLACA               │  ┌──────────────────────────────┐    │  Placas: 2            │
│ ▸ PIEZAS              │  │  QGraphicsView a escala      │    │  Área total: 10.32 m² │
│ ▸ PARÁMETROS          │  │  (zoom, pan, selección)      │    │  Utilizada: 9.02 m²   │
│                       │  └──────────────────────────────┘    │  Desperdicio: 1.30 m² │
│                       │  Leyenda: ■Lateral ■Tapa ■Puerta …   │  Aprovech.: 87.4 %    │
│ ┌───────────────────┐ │ ─────────────────────────────────────│  Piezas: 18           │
│ │ OPTIMIZAR CORTES  │ │  [Lista de cortes] [Secuencia]       │ PLACAS (por placa %)  │
│ └───────────────────┘ │  [Retazos]   (tabs inferiores)       │ DESPERDICIO / RETAZOS │
├───────────────────────┴──────────────────────────────────────┴───────────────────────┤
│ Barra de estado: proyecto · placa seleccionada · estrategia ganadora · tiempo · aviso │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Splitters redimensionables; estado de la ventana guardado con `QSettings`.

## 2. Widgets

| Widget | Archivo | Contenido |
|--------|---------|-----------|
| Proyecto | `project_widget.py` | Nombre, descripción, mueble(s) del proyecto, dimensiones generales (opcional, preparado para generador) |
| Datos de la placa | `plate_widget.py` | Nombre, ancho, alto, espesor, material, color, proveedor, veta de placa; botón **Guardar placa**; lista de placas guardadas (seleccionar / duplicar / eliminar); stock disponible |
| Lista de piezas | `pieces_widget.py` | `QTableView` + modelo editable: Nombre, Categoría, Cantidad, Ancho, Alto, Espesor, Material, Rotación (check), Veta (combo), Orientación fija (check). Botones: Agregar, Duplicar, Eliminar, Subir/Bajar. Validación en línea (celda roja + tooltip) |
| Parámetros | `parameters_widget.py` | Kerf, margen, separación, rotación global, nivel (rápida/equilibrada/máxima), modo (escuadradora/CNC), usar stock primero, usar retazos, tamaño mínimo de retazo |
| Diagrama | `cutting_diagram_widget.py` | Una pestaña por placa; escena a escala 1 unidad = 1 mm |
| Resultado | `result_widget.py` | Tarjetas KPI + tabla por placa (%, usado, desperdicio) |
| Lista de cortes | `cut_list_widget.py` | Nº, Pieza, Ancho, Alto, Placa, X, Y, Rotación; ordenable; clic ⇒ resalta en el diagrama |
| Secuencia | `cut_list_widget.py` (tab) | CORTE n, nivel, orientación, medida, longitud |
| Retazos | `offcuts_widget.py` | Retazos del resultado + botón "Guardar en stock"; vista de retazos disponibles |
| Inventario | `inventory_widget.py` | Diálogo: formatos y cantidad disponible |

## 3. Diagrama de placa (QGraphicsScene)

- Rectángulo de placa (borde oscuro) + franja de margen sombreada.
- Pieza = `QGraphicsRectItem` personalizado (`PieceItem`) con:
  - Relleno por categoría, borde 1 px cosmético.
  - Texto: `"Lateral 1"`, `"400 × 600"`, icono ⟲ si rotada, flecha de veta.
  - Texto con `ItemIgnoresTransformations` o escalado adaptativo para legibilidad en zoom.
  - Tooltip con coordenadas exactas.
- Retazo reutilizable: verde claro con rayado diagonal + etiqueta "Retazo 600 × 400".
- Desperdicio: gris.
- Líneas de corte (opcional, toggle): numeradas según la secuencia.
- Cotas en bordes (opcional).
- Eje Y: origen arriba-izquierda (convención de taller y de Qt). Se documenta en la leyenda.

**Regla de oro**: el diagrama se dibuja **solo** a partir de `Placement` reales; no hay rectángulos decorativos.

## 4. Colores por categoría (`ui/theme.py`)

| Categoría | Color | Hex |
|-----------|-------|-----|
| Lateral | Azul | `#4A90D9` |
| Tapa / Base | Verde | `#5CB85C` |
| Fondo | Violeta | `#9B7FD4` |
| Puerta | Amarillo | `#F0C419` |
| Divisor | Rojo | `#D9534F` |
| Estante | Turquesa | `#2EC4B6` |
| Cajón | Naranja | `#F39C12` |
| Otro | Celeste grisáceo | `#8FA9C1` |
| Retazo reutilizable | Verde claro rayado | `#C8E6C9` |
| Desperdicio | Gris | `#BDBDBD` |

Leyenda generada desde el mismo diccionario (fuente única). Contraste del texto calculado automáticamente (negro/blanco).

## 5. Flujo de usuario

1. **Nuevo proyecto** (o se abre la demo).
2. **Seleccionar placa** de la lista (o crear y "Guardar placa").
3. **Introducir piezas** en la tabla.
4. **Ajustar parámetros**.
5. **OPTIMIZAR CORTES** → barra de progreso, botón Cancelar; la UI sigue respondiendo.
6. Ver placas en el panel central; resumen a la derecha.
7. Revisar desperdicio y retazos.
8. Revisar lista y secuencia de cortes.
9. **Exportar PDF / CSV**.

## 6. Unidades

`units_display.py`: el usuario elige mm/cm/m en el menú Ver; afecta a etiquetas, tablas y resumen. La **entrada** se interpreta en la unidad visible y se convierte a mm con `Decimal` (sin floats). Áreas siempre en m².

## 7. Errores y validaciones

- Errores de validación: panel de mensajes con lista clicable (lleva a la fila/campo).
- Piezas no ubicadas: aviso destacado en el resultado + lista con motivo ("mayor que la placa en ambas orientaciones permitidas por la veta").
- Nunca `QMessageBox` para errores masivos; sí para confirmaciones (eliminar proyecto).

## 8. Estilo

Tema claro moderno con QSS (fuente del sistema, bordes redondeados, botón primario grande "OPTIMIZAR CORTES"), soporte de modo oscuro básico con la misma paleta de categorías.
