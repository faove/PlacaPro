# Sprint 6 — Exportación, inventario y retazos

**Objetivo**: llevar el resultado al taller (PDF/CSV) y gestionar stock de placas y retazos reutilizables.

**Requisitos cubiertos**: RF-08 (UI), RF-09, RF-10, §14, §15, §22.

## Alcance

### 1. Exportadores (`exporters/`)
- [ ] `base.py`: `Protocol Exporter { id, name, file_filter, export(project, result, path, options) }` + registry `EXPORTERS` (menú Exportar generado dinámicamente).
- [ ] `pdf_exporter.py` (`QPdfWriter` + `QPainter`, A4):
  - **Página 1**: información del proyecto (nombre, fecha, muebles, placa, parámetros de corte).
  - **Página 2**: resumen de materiales (placas por formato, áreas, aprovechamiento, retazos, lista de piezas agregada).
  - **Página 3..n**: una placa por página: diagrama a escala (mismo renderizado que la UI, reutilizando `SheetScene.render()`), tabla de piezas con X/Y/rotación, secuencia de cortes.
  - Pie con número de página y nombre del proyecto.
- [ ] `csv_exporter.py`: `piezas.csv` (lista de piezas del proyecto) y `cortes.csv` (Nº, Pieza, Ancho, Alto, Placa, X, Y, Rotación + secuencia), separador `;`, UTF-8 con BOM (compatible con Excel en español).
- [ ] `services/report_service.py`: orquesta exportadores y nombres de archivo por defecto.

### 2. Inventario (`ui/inventory_widget.py`)
- [ ] Diálogo: formatos con cantidad disponible editable.
- [ ] Opción "Utilizar primero las placas existentes" ya conectada al optimizador (sprint 2) — verificar en UI.
- [ ] Al **confirmar** un plan de corte (botón "Confirmar y descontar stock"): descontar placas de inventario usadas y marcar retazos consumidos (transacción).

### 3. Retazos (`ui/offcuts_widget.py`)
- [ ] Tabla de retazos del resultado actual (dimensiones, placa, estado) con "Guardar en stock".
- [ ] Sección **Retazos disponibles**: filtro por material/espesor, eliminar, marcar consumido.
- [ ] Opción "Usar retazos primero" en parámetros.

## Tests del sprint
- `test_exporters.py`: el PDF existe, tiene `2 + nº_placas` páginas (comprobado con `pypdf` como dependencia de test o contando `/Type /Page`); el CSV tiene una fila por pieza colocada y los valores coinciden con el resultado.
- `test_inventory.py`: confirmar plan descuenta stock; no se permite stock negativo.
- `test_offcuts_flow.py`: guardar retazo → aparece disponible → una optimización lo usa → queda consumido.

## Criterios de aceptación
- Exportar la demo genera un PDF legible de ≥ 3 páginas y dos CSV que abren correctamente en LibreOffice/Excel.
- Añadir un nuevo exportador solo requiere un archivo nuevo + registro (demostrar con un `SvgExporter` mínimo opcional).

## Resultado
_(completar al cerrar el sprint)_
