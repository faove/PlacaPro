# Sprint 0 — Fundaciones

**Objetivo**: entorno reproducible, estructura del proyecto y utilidades numéricas exactas sobre las que se apoya todo lo demás.

**Requisitos cubiertos**: RF-11, RNF-02 (esqueleto), RNF-04, RNF-07 (infraestructura de tests).

## Alcance

### 1. Entorno
- [ ] Python 3.11+ en `venv` (el sistema trae 3.8.10 → ver riesgo B1).
- [ ] `requirements.txt`: `PySide6>=6.6`, `pytest`, `pytest-qt`, `hypothesis`, `pytest-cov` (separar `requirements-dev.txt` para las de test).
- [ ] `pyproject.toml` con configuración de pytest (`testpaths`, marcadores `slow`, `ui`) y ruff.
- [ ] `.gitignore`, `git init`.

### 2. Estructura
- [ ] Crear todas las carpetas de [01-arquitectura.md §3](../01-arquitectura.md#3-estructura-de-carpetas) con `__init__.py`.
- [ ] `app.py` mínimo: abre una `QMainWindow` vacía con título "PlacaPro".

### 3. `utils/units.py`
- [ ] `INTERNAL_PER_MM = 10` (décimas de mm).
- [ ] `parse_length(text: str, unit: Unit) -> Decimal` (acepta `,` y `.` decimal; rechaza >1 decimal en mm, negativos, vacío).
- [ ] `mm_to_internal(Decimal) -> int`, `internal_to_mm(int) -> Decimal`.
- [ ] `format_length(int_internal, unit: Unit, decimals=1) -> str` para mm / cm / m.
- [ ] `area_internal_to_m2(int) -> Decimal`.
- [ ] Enum `Unit {MM, CM, M}`.

### 4. `utils/geometry.py`
- [ ] `Rect(x, y, w, h)` inmutable con enteros: `right`, `bottom`, `area`, `intersects`, `contains`, `intersection`, `gap_to(other)` (separación mínima horizontal/vertical).
- [ ] `fits(w, h, container_w, container_h)`.
- [ ] `subtract(rect, used) -> list[Rect]` (base para MaxRects).

### 5. `utils/constants.py`
- [ ] Formatos estándar de placa, kerf por defecto (3.2), margen por defecto (10), mínimos de retazo, nombre de app, ruta por defecto de la DB.

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
_(completar al cerrar el sprint)_
