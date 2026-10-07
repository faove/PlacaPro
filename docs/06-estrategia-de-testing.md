# 06 — Estrategia de testing

## 1. Herramientas
- `pytest`, `pytest-qt` (tests de widgets), `hypothesis` (tests basados en propiedades), `pytest-cov`.
- Comando: `pytest -q` · cobertura: `pytest --cov=models --cov=optimization --cov=services --cov=utils`.
- Objetivo de cobertura: ≥ 90 % en `optimization/` y `utils/`, ≥ 80 % en `services/` y `database/`.

## 2. Pirámide

| Nivel | Qué | Ejemplos |
|-------|-----|----------|
| Unitarios | utils, orientación, packers, scoring, validación | `test_units.py`, `test_geometry.py`, `test_orientation.py` |
| Propiedades | invariantes sobre entradas aleatorias | `test_optimizer_properties.py` |
| Integración | servicios + SQLite en memoria + exportadores | `test_services.py`, `test_repositories.py`, `test_exporters.py` |
| UI (smoke) | ventana abre, demo carga, botón optimizar produce escena | `test_ui_smoke.py` (pytest-qt, `QT_QPA_PLATFORM=offscreen`) |
| E2E | demo "Mesita de noche" completa → PDF/CSV generados | `test_demo_mesita.py` |

## 3. Casos obligatorios del cliente (§19)

| # | Caso | Test | Resultado esperado |
|---|------|------|--------------------|
| 1 | Pieza que cabe perfectamente | `test_exact_fit` | Placa 1000×1000, margen 0, kerf 0, pieza 1000×1000 → 1 placa, 100 % |
| 2 | Pieza que no cabe | `test_piece_does_not_fit` | Aparece en `unplaced` + `ValidationIssue` claro, no excepción |
| 3 | Rotación | `test_rotation_enables_fit` | Pieza 2000×500 en placa 1000×2500 → colocada rotada |
| 4 | Pieza que no puede rotarse | `test_no_rotation_respected` | Misma pieza con `can_rotate=False` → no ubicada |
| 5 | Kerf | `test_kerf_between_pieces` | 2 piezas 500 en placa útil 1003.2 caben; en 1003.1 no |
| 6 | Margen | `test_margin_respected` | Ninguna pieza con x < m ni x+w > W−m |
| 7 | Varias placas | `test_multiple_sheets` | 3 piezas que ocupan > 1 placa → 2 placas, sin solapes |
| 8 | Piezas duplicadas | `test_quantity_expansion` | cantidad 4 → 4 instancias etiquetadas 1..4, todas colocadas |
| 9 | Pieza mayor que la placa | `test_oversized_piece_validation` | Error de validación antes de optimizar |
| 10 | Diferentes tamaños | `test_mixed_sizes_quality` | Conjunto de referencia: nº placas ≤ referencia conocida |

Adicionales:
- `test_grain_vertical_never_rotated`, `test_grain_horizontal_rotated_on_plate_along_height`.
- `test_guillotine_layout_is_guillotinable` y `test_cut_sequence_reconstructs_pieces` (aplicar la secuencia de cortes a la placa produce exactamente las piezas).
- `test_offcut_classification`.
- `test_deterministic_with_seed`.
- `test_lower_bound_reached_simple_cases`.
- `test_units_no_float_error` (`Decimal("3.2")*3`, conversiones ida y vuelta).
- `test_project_crud_duplicate_delete`.

## 4. Propiedades (Hypothesis)

Para cualquier conjunto aleatorio de piezas válidas y parámetros válidos:
1. **No solapes**, separación ≥ kerf entre piezas.
2. **Dentro de los márgenes**.
3. **Conservación**: colocadas + no colocadas = instancias de entrada (sin duplicar ni perder).
4. **Dimensiones exactas** (posiblemente intercambiadas si rotada y permitido).
5. **Orientación válida** según veta.
6. `sheets_used ≥ lower_bound`.
7. En `PANEL_SAW`, todo layout es guillotinable y la secuencia reconstruye las piezas.
8. `used_area + waste_area == total_area` (exacto en enteros).

## 5. Benchmarks
`tests/benchmarks/` (marcados `@pytest.mark.slow`): instancias de 20, 50, 100, 200 piezas; registrar placas, aprovechamiento y tiempo por nivel en `docs/benchmarks.md` al final de cada sprint que toque el optimizador.
