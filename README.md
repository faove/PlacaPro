# PlacaPro

Aplicación de escritorio para **optimizar el corte de placas** de melamina, MDF o madera en la fabricación de muebles. Se cargan las piezas de un mueble y PlacaPro calcula cómo distribuirlas en el menor número de placas. Respeta el espesor de la sierra (kerf), el refilado de los bordes y la veta. Muestra cada placa a escala junto con la secuencia de cortes para la escuadradora. El plan se puede exportar a PDF o CSV.

![Ventana principal con la demo «Mesita de noche»](docs/img/sprint-07-ventana.png)

Está hecha en Python con PySide6 (Qt) y SQLite. Funciona en Linux, Windows y macOS, sin conexión.

---

## 1. Instalación

### Requisitos
- **Python 3.11 o superior** (probado con 3.12).
- Dependencias de Python: `PySide6` para ejecutar. Para desarrollar también `pytest`, `pytest-qt`, `pytest-cov`, `hypothesis` y `ruff`.
- **Linux**: las bibliotecas de sistema que necesita Qt. En Debian o Ubuntu:

  ```bash
  sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1 libfontconfig1 libdbus-1-3
  ```

  En Fedora el equivalente es `sudo dnf install xcb-util-cursor libxkbcommon-x11 mesa-libEGL`. Si falta alguna, Qt avisa al arrancar con `Could not load the Qt platform plugin "xcb"`.

### Pasos

```bash
git clone <repositorio> PlacaPro
cd PlacaPro
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # solo para usar la aplicación
pip install -r requirements-dev.txt  # además, para ejecutar los tests
```

### Ejecutar

```bash
python app.py
```

La primera vez se crea la base de datos con los materiales, los formatos de placa estándar y el proyecto de demostración **«Mesita de noche»**. La demo se optimiza automáticamente, así que el resultado aparece apenas se abre la ventana.

Los datos quedan en la carpeta `~/.placapro/` (en Windows, `%USERPROFILE%\.placapro\`). Allí están `placapro.db`, que es la base, y `placapro.log`, el registro de errores. Para usar otra base se puede definir la variable de entorno `PLACAPRO_DB=/ruta/a/otra.db`. Si se borra la base, la aplicación vuelve a empezar desde cero, con la demo.

---

## 2. Uso paso a paso

La ventana tiene tres zonas:

- **Izquierda**: los datos del proyecto, en las secciones PROYECTO, PLACA, PIEZAS y PARÁMETROS, con el botón **OPTIMIZAR CORTES** debajo.
- **Centro**: el diagrama de las placas y, debajo, las pestañas Lista de cortes, Secuencia, Retazos y Mensajes.
- **Derecha**: el resumen del resultado.

### 2.1 Crear una placa
1. Abra la sección **PLACA**.
2. Pulse **Nueva** y complete nombre, ancho, alto, espesor, material, color y veta.
3. Pulse **Guardar placa**. La placa seleccionada en la lista es la que usa el proyecto.

Ya vienen cargados los formatos más comunes, por ejemplo 1830 × 2820 × 18 mm.

### 2.2 Crear un proyecto
Use **Archivo ▸ Nuevo** (`Ctrl+N`) y escriba el nombre en **PROYECTO**. Un proyecto puede tener varios muebles, cada uno con su propia lista de piezas.

Para guardar, use **Guardar** (`Ctrl+S`) o **Guardar como** (`Ctrl+Shift+S`). Para abrir uno existente, **Abrir** (`Ctrl+O`).

### 2.3 Agregar piezas
En **PIEZAS**, pulse **Agregar** y edite la fila directamente en la tabla. Cada pieza tiene:

- nombre;
- cantidad;
- ancho y alto;
- espesor;
- categoría, que define el color en el diagrama;
- veta;
- si puede girarse.

La tabla se valida mientras se escribe. Las celdas con errores se pintan de rojo y al pasar el mouse explican qué corregir. Por ejemplo: *«La pieza «Puerta» (482 × 2900 mm) no cabe en la placa 1830 × 2820 con la veta vertical (…); reduzca el alto»*.

### 2.4 Optimizar
Pulse **OPTIMIZAR CORTES** (o `Ctrl+Enter` / `F5`). El cálculo corre en segundo plano con una barra de progreso, y se puede **Cancelar** en cualquier momento.

El botón queda deshabilitado mientras haya **errores** (en rojo) en la pestaña **Mensajes**; si se hace clic en un mensaje, la aplicación lleva al campo que hay que corregir. Las **advertencias** (en naranja), como un material distinto al de la placa, no impiden optimizar.

En **PARÁMETROS** se elige el nivel de búsqueda:

| Nivel | Tiempo aproximado con 100 piezas |
|---|---|
| Rápida | instantáneo |
| Equilibrada | menos de 1 s |
| Máxima | unos 4 s |

Ver [docs/benchmarks.md](docs/benchmarks.md).

### 2.5 Confirmar el plan y llevar el stock
- **Datos ▸ Inventario de placas** guarda cuántas placas enteras hay de cada formato.
- La pestaña **Retazos** sirve para guardar en stock los sobrantes reutilizables de un resultado. Luego se pueden usar en otro proyecto activando *Usar retazos del stock* en PARÁMETROS.
- **Confirmar y descontar stock** descuenta las placas usadas y marca como consumidos los retazos usados. Se hace una sola vez por resultado y solo si el resultado está al día con los datos.

---

## 3. Cómo interpretar el resultado

| Indicador | Definición |
|---|---|
| **Placas necesarias** | Placas (o retazos de stock) que hay que cortar |
| **Área total** | Suma del área de todas las placas usadas, con sus bordes |
| **Área utilizada** | Suma del área de las piezas |
| **Desperdicio** | Área total − área utilizada. Incluye todo lo que no es pieza: kerf, refilado, retazos y recortes chicos |
| **Aprovechamiento** | Área utilizada ÷ área total |
| **Retazos reutilizables** | Parte del desperdicio que se puede guardar: sobrantes que superan el ancho, el alto y el área mínimos de PARÁMETROS (150 × 150 mm y 0,05 m² por defecto) |
| **Cota inferior** | ⌈área de piezas con kerf ÷ área útil de una placa⌉. Si el resultado la iguala, ninguna solución usa menos placas |

**Retazo frente a desperdicio.** Todo sobrante rectangular que queda después de cortar es un **retazo reutilizable** (rayado en el diagrama) si es lo bastante grande para otro trabajo. Si no lo es, es **desperdicio** (gris). El kerf (el aserrín) y la franja del refilado siempre son desperdicio.

En cada placa se cumple: piezas + kerf + retazos + desperdicio = área de la placa. Los tests lo verifican.

En el diagrama, cada pieza muestra su nombre y medidas, y la flecha ↕/↔ indica la veta. Al hacer clic en una pieza o un corte se resalta la fila correspondiente en la lista, y viceversa. Si los datos cambian después de optimizar, aparece el aviso **«Resultado desactualizado»**.

---

## 4. Kerf y margen

Se configuran en **PARÁMETROS ▸ Corte**. Pasando el mouse sobre cada campo se ve una explicación con ejemplos.

- **Kerf**: ancho del corte de la sierra; por defecto 3,2 mm. Se descuenta solo **entre** piezas, no contra el borde de la placa.
- **Margen de refilado**: franja que se descarta en cada borde de la placa porque suele venir dañada o fuera de escuadra; por defecto 10 mm.
- **Separación adicional**: holgura extra entre piezas además del kerf. Normalmente es 0.

**Ejemplo numérico.** Placa de 1830 mm de ancho, margen de 10 mm y kerf de 3,2 mm, con dos piezas de 500 mm en fila:

```
pieza 1:  x = 10            → ocupa [10, 510]
kerf:                          [510, 513,2]
pieza 2:  x = 513,2         → ocupa [513,2, 1013,2]
…
la última pieza termina como máximo en 1830 − 10 = 1820
```

La superficie útil de la placa es 1810 × 2800 mm (1830 − 2·10 por 2820 − 2·10). Si en lugar de 3,2 se configura un kerf de 3 mm, la segunda pieza empieza en x = 513. Las coordenadas se muestran con un decimal, que es la precisión interna (0,1 mm).

---

## 5. Veta

La veta de la **pieza** se indica respecto de sus propias medidas:

- **Vertical**: la veta corre a lo largo del alto.
- **Horizontal**: la veta corre a lo largo del ancho.
- **Indiferente**: la pieza no tiene veta.

La veta de la **placa** se define en PLACA. Si las dos tienen veta, la pieza se gira lo necesario para alinearlas, **aunque la rotación esté desactivada**: la veta siempre manda.

| Veta de la placa | Veta de la pieza | Orientaciones permitidas |
|---|---|---|
| cualquiera | Indiferente, giro permitido y rotación activada en PARÁMETROS | 0° y 90° |
| cualquiera | Indiferente, pero «no girar», orientación fija o rotación desactivada | solo 0° |
| A lo largo del alto | Vertical | 0° (ya está alineada) |
| A lo largo del alto | Horizontal | 90° (hay que girarla) |
| A lo largo del ancho | Vertical | 90° |
| A lo largo del ancho | Horizontal | 0° |
| Sin veta | Vertical u Horizontal | 0° (se respeta como se dibujó) |

Si una pieza no cabe por culpa de la veta, el mensaje lo dice y sugiere qué cambiar. Por ejemplo: *«cabría girada: cambie la veta a «Indiferente» o reduzca el ancho»*.

---

## 6. Exportar

**Archivo ▸ Exportar** (`Ctrl+E` exporta directamente a PDF):

- **PDF (A4)**:
  - página 1 con los datos del proyecto (muebles, placa y parámetros de corte);
  - página 2 con el resumen de materiales, los retazos y la lista de piezas;
  - una página por placa, con el diagrama a escala (cortes y cotas), la leyenda, las piezas con X/Y/rotación y la secuencia de cortes numerada.
  - Si una tabla no entra en su página, continúa en la siguiente marcada «(cont.)».
- **CSV**: dos archivos, `<nombre>_piezas.csv` y `<nombre>_cortes.csv` (lista de cortes y secuencia). Usan separador `;`, coma decimal y codificación UTF-8 con BOM, de modo que Excel en español los abre bien.
- **SVG**: un archivo por placa, con el mismo dibujo que el diagrama.

Todos usan la unidad elegida en **Ver ▸ Unidades** (mm, cm o m).

---

## 7. Cómo funciona el algoritmo

El problema es un *bin packing* rectangular 2D con rotación restringida. Es NP-difícil, así que PlacaPro usa heurísticas constructivas y búsqueda multi-arranque, y verifica cada solución. El detalle completo está en [docs/03-algoritmo-de-optimizacion.md](docs/03-algoritmo-de-optimizacion.md).

1. **Transformación**: el kerf se suma a cada pieza y a la superficie útil (`w' = w + k`, `W_u = W − 2m + k`). Así, entre dos piezas vecinas queda siempre exactamente un kerf, y el sobrante final cae dentro del margen de refilado. Todo se calcula con **enteros en décimas de milímetro**, sin errores de redondeo.
2. **Orientaciones**: para cada pieza se calculan las orientaciones admitidas según la veta, la orientación fija y la rotación (tabla del §5).
3. **Colocación**: se usa *Guillotine* con varias reglas de elección de hueco y de división, y *MaxRects*. Las piezas se van colocando placa por placa o eligiendo el mejor encaje global.
4. **Búsqueda**: se prueban muchos ordenamientos (por área, lado mayor, perímetro…) y perturbaciones aleatorias con semilla fija, de modo que el resultado es reproducible. El nivel *Máxima* añade búsqueda local para intentar vaciar la última placa.
5. **Verificación**: cada candidato se comprueba de forma independiente: sin solapes, dentro del margen, separación ≥ kerf, medidas exactas y orientación permitida. Una solución que falla se descarta.

### Por qué la puntuación es lexicográfica

El enunciado proponía `placas × 1.000.000 + desperdicio + cortes × penalización`. Pero con un número fijo de placas el desperdicio total es **constante** (área de placas − área de piezas), así que ese término no distingue entre soluciones. Además, cualquier peso numérico entre criterios acaba siendo arbitrario.

Por eso las soluciones se comparan como una tupla, criterio por criterio:

```
(piezas sin colocar, placas, −retazos de stock aprovechados, área de la placa menos llena,
 −sobrante cortable más grande, nº de cortes, longitud de corte)
```

Primero se minimizan las placas. Después se busca que la última placa quede lo más vacía posible y que los sobrantes sean grandes y reutilizables en vez de muchos pedazos chicos. Recién al final cuentan los cortes. Un criterio menos importante nunca compensa a uno más importante.

### Optimización matemática y plan de corte físico

Son dos etapas separadas a propósito:

- **Optimización** (`optimization/packing.py`, `optimizer.py`): decide *dónde* va cada pieza. Su resultado son rectángulos con coordenadas.
- **Plan de corte** (`optimization/guillotine.py`, `cutting.py`): decide *cómo* cortar esa distribución en la escuadradora.
  - Descompone la placa en cortes de borde a borde, en etapas: primero el refilado, luego tiras y después piezas.
  - Numera la secuencia, calcula el kerf de cada corte y separa los sobrantes en retazos y desperdicio.
  - Si una distribución no se puede cortar así, en modo escuadradora se descarta. En modo CNC se admite y se informan los contornos.

Los tests simulan la secuencia de cortes sobre la placa y comprueban que salen exactamente las piezas y los sobrantes previstos. Ver [docs/04-plan-de-corte-fisico.md](docs/04-plan-de-corte-fisico.md).

---

## 8. Tests

```bash
pytest                       # suite completa (los tests de interfaz usan Qt offscreen)
pytest -m "not ui"           # solo dominio, optimizador y servicios
pytest --cov                 # con cobertura
ruff check . && ruff format --check .
python scripts/benchmark.py  # rendimiento; --write actualiza docs/benchmarks.md
```

| Archivo | Qué prueba |
|---|---|
| `tests/test_demo_mesita.py` | Punta a punta: datos iniciales → optimizar → verificar invariantes → reconstruir piezas con el plan de corte → exportar PDF y CSV |
| `tests/test_optimizer_properties.py` | Propiedades con *hypothesis*: sin solapes, dentro de la placa, kerf, veta, determinismo |
| `tests/test_ui_smoke.py` | Recorre la ventana completa |

La estrategia completa de tests está en [docs/06-estrategia-de-testing.md](docs/06-estrategia-de-testing.md).

---

## 9. Estructura

```
app.py            punto de entrada
models/           entidades del dominio y validaciones (sin Qt)
database/         SQLite: esquema, migraciones, repositorios, datos iniciales
optimization/     packing, búsqueda, verificación, plan de corte, retazos (sin Qt)
services/         casos de uso: proyectos, placas, optimización, inventario, informes
exporters/        PDF, CSV, SVG (un archivo + registro por formato)
ui/               ventana y paneles PySide6
docs/             análisis, arquitectura, sprints y benchmarks
```

`models`, `database`, `services`, `optimization` y `utils` no importan Qt, y hay un test que lo controla. Se puede **agregar un formato de exportación** creando un módulo en `exporters/` con `register(...)` y nombrándolo en `FORMAT_MODULES`.

Lo previsto para versiones futuras (generador de despiece por medidas, costos, DXF/G-code) está en [docs/08-roadmap-futuro.md](docs/08-roadmap-futuro.md). Ya existe la base:

- `DeskGenerator` experimental en `services/furniture_generator.py`;
- `CostService` con sus entidades y las tablas de costos.

## Atajos de teclado

| Atajo | Acción |
|---|---|
| `Ctrl+N` / `Ctrl+O` | Nuevo / abrir proyecto |
| `Ctrl+S` / `Ctrl+Shift+S` | Guardar / guardar como |
| `Ctrl+Enter` o `F5` | Optimizar |
| `Ctrl+E` | Exportar PDF |
| `Ctrl+Q` | Salir |
