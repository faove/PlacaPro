# Sprint 0 — Fundaciones

**Objetivo**: entorno reproducible, estructura del proyecto y utilidades numéricas exactas sobre las que se apoya todo lo demás.

**Requisitos cubiertos**: RF-11, RNF-02 (esqueleto), RNF-04, RNF-07 (infraestructura de tests).

## Alcance

### 1. Entorno
- [x] Python 3.11+ en `venv` (el sistema trae 3.8.10 → ver riesgo B1).
- [x] `requirements.txt`: `PySide6>=6.6`, `pytest`, `pytest-qt`, `hypothesis`, `pytest-cov` (separar `requirements-dev.txt` para las de test).
- [x] `pyproject.toml` con configuración de pytest (`testpaths`, marcadores `slow`, `ui`) y ruff.
- [x] `.gitignore`, `git init`.

### 2. Estructura
- [x] Crear todas las carpetas de [01-arquitectura.md §3](../01-arquitectura.md#3-estructura-de-carpetas) con `__init__.py`.
- [x] `app.py` mínimo: abre una `QMainWindow` vacía con título "PlacaPro".

### 3. `utils/units.py`
- [x] `INTERNAL_PER_MM = 10` (décimas de mm).
- [x] `parse_length(text: str, unit: Unit) -> Decimal` (acepta `,` y `.` decimal; rechaza >1 decimal en mm, negativos, vacío).
- [x] `mm_to_internal(Decimal) -> int`, `internal_to_mm(int) -> Decimal`.
- [x] `format_length(int_internal, unit: Unit, decimals=1) -> str` para mm / cm / m.
- [x] `area_internal_to_m2(int) -> Decimal`.
- [x] Enum `Unit {MM, CM, M}`.

### 4. `utils/geometry.py`
- [x] `Rect(x, y, w, h)` inmutable con enteros: `right`, `bottom`, `area`, `intersects`, `contains`, `intersection`, `gap_to(other)` (separación mínima horizontal/vertical).
- [x] `fits(w, h, container_w, container_h)`.
- [x] `subtract(rect, used) -> list[Rect]` (base para MaxRects).

### 5. `utils/constants.py`
- [x] Formatos estándar de placa, kerf por defecto (3.2), margen por defecto (10), mínimos de retazo, nombre de app, ruta por defecto de la DB.

## Tests del sprint
- `test_units.py`: ida y vuelta mm↔interno, `"1830"`, `"1830,5"`, `"3.2"`, rechazo de `"3.25"`, `"-1"`, `"abc"`; formateo cm/m; ausencia de errores de float (`3.2 × 3 = 9.6` exacto).
- `test_geometry.py`: bordes adyacentes no cuentan como solape, contención, gap, subtract.

## Criterios de aceptación
- `pytest` en verde.
- `python app.py` abre una ventana vacía.
- Ninguna función de `utils` usa `float` para longitudes.

## Entregables
Estructura del repo, `requirements*.txt`, `utils/*`, tests.

## Resultado
**Estado: cerrado (2026-10-07).**

- Entorno: Python **3.12.15** instalado con `uv` (sin sudo, en `~/.local/share/uv`), venv en `.venv/`. PySide6 **6.9.3** funciona con X11 y en modo `offscreen`.
- Puesta en marcha para desarrolladores:
  ```bash
  ~/.local/bin/uv venv --python 3.12 .venv
  ~/.local/bin/uv pip install --python .venv/bin/python -r requirements-dev.txt
  .venv/bin/python app.py
  .venv/bin/python -m pytest
  ```
- `utils/units.py`: además de lo planificado, `to_unit()` y `format_area_m2()`; se rechazan `float` y `bool` como longitudes (`TypeError`). Formato con coma decimal por defecto.
- `utils/geometry.py`: `Rect.separation()` (en vez de `gap_to`) devuelve el mayor hueco entre ejes: negativo = solape, 0 = se tocan, ≥ kerf = cortable. Se añadió `prune_contained()` para MaxRects.
- Tests: **56 pasan** (`test_units.py`, `test_geometry.py` con Hypothesis, `test_app.py` con pytest-qt). Cobertura de `utils/`: 97 %.
- `ruff check` sin avisos.
- Se ejecutó `git init`; todavía no hay commits.
