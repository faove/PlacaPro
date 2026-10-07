# Sprint 7 — Validación, pulido y entrega

**Objetivo**: robustez, experiencia de usuario, demo automática, prueba completa y documentación final.

**Requisitos cubiertos**: RF-12, RF-13, §19, §24, §28, §31 (pasos 11–14), §33, §35.

## Alcance

### 1. Validaciones completas (RF-12)
- [ ] Revisión de todos los códigos: `PIECE_LARGER_THAN_PLATE`, `NON_POSITIVE_DIMENSION`, `ZERO_QUANTITY`, `THICKNESS_MISMATCH`, `INVALID_KERF`, `MARGIN_TOO_LARGE`, `UNPLACEABLE_PIECE`, `MATERIAL_MISMATCH`.
- [ ] Mensajes en español, accionables ("La pieza «Puerta» (482 × 2900) no cabe en la placa 1830 × 2820 con la veta vertical; reduzca el alto o cambie la veta").
- [ ] Validación en línea en la tabla + bloqueo del botón optimizar con errores bloqueantes (advertencias no bloquean).

### 2. Demo "Mesita de noche" (RF-13)
- [ ] Al primer arranque (DB nueva) se abre la demo y se optimiza automáticamente.
- [ ] Piezas: 2 × 400×600 (Lateral), 1 × 564×400 (Tapa), 1 × 564×600 (Fondo), 2 × 282×600 (Puerta), 1 × 564×100 (Zócalo/Divisor) sobre placa 1830×2820×18, kerf 3.2, margen 10.

### 3. Prueba E2E
- [ ] `test_demo_mesita.py`: seed → optimizar → verificar invariantes → plan de corte reconstruye piezas → exportar PDF y CSV a `tmp_path`.
- [ ] Prueba manual guiada (checklist en este documento) de los 9 pasos del flujo de usuario.
- [ ] Ejecutar la suite completa + benchmarks; actualizar `docs/benchmarks.md`.

### 4. Pulido
- [ ] Tema visual final (QSS), iconos, atajos (Ctrl+N/O/S/Shift+S, Ctrl+Enter = optimizar, Ctrl+E = exportar).
- [ ] Tooltips explicativos de kerf, margen y veta en el panel de parámetros.
- [ ] Revisar rendimiento con 200 piezas (UI fluida, cancelación inmediata).
- [ ] Revisar textos y ortografía.

### 5. Preparación para el futuro (sin UI)
- [ ] `FurnitureGenerator`: ejemplo `DeskGenerator` mínimo documentado en código (marcado experimental, no expuesto en la UI) que demuestra el pipeline Dimensiones → Despiece → Piezas → Optimizador.
- [ ] `CostService` con entidades y tablas listas; test que verifica la firma.

### 6. README.md (raíz) — §33
- [ ] Instalación (Python 3.11+, venv, dependencias de sistema Qt en Linux), dependencias, cómo ejecutar.
- [ ] Cómo crear una placa, un proyecto, agregar piezas, ejecutar la optimización.
- [ ] Cómo interpretar el resultado (definiciones de área, aprovechamiento, retazo vs desperdicio).
- [ ] Cómo modificar kerf y margen (con el ejemplo numérico de 513,2).
- [ ] Cómo trabajar con veta (tabla de orientaciones).
- [ ] Cómo exportar (PDF/CSV).
- [ ] Explicación técnica del algoritmo (resumen de [03](../03-algoritmo-de-optimizacion.md) + por qué el score es lexicográfico).
- [ ] Separación optimización matemática / plan de corte físico.
- [ ] Cómo ejecutar los tests.

## Checklist de prueba manual
1. [ ] Crear proyecto "Mueble bajo".
2. [ ] Seleccionar placa 1830 × 2820 × 18.
3. [ ] Introducir las 5 piezas del ejemplo del enunciado (laterales 700×500, tapa/base 964×500, fondo 964×664, puertas 482×700).
4. [ ] Kerf 3,2; margen 10; equilibrada.
5. [ ] OPTIMIZAR.
6. [ ] Placas visibles, a escala, con leyenda.
7. [ ] Desperdicio y retazos coherentes.
8. [ ] Lista de cortes con X/Y verificables a mano para 2 piezas.
9. [ ] Exportar PDF y CSV.

## Criterios de aceptación (entrega final)
- `python app.py` → aplicación funcional con la demo optimizada.
- `pytest` en verde, cobertura objetivo alcanzada.
- README completo; documentos de `docs/` actualizados con la sección *Resultado* de cada sprint.

## Resultado
_(completar al cerrar el sprint)_
