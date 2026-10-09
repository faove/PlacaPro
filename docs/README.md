# PlacaPro — Documentación del proyecto

Aplicación de escritorio en Python (PySide6 + SQLite) para **optimizar cortes de placas de melamina / MDF / madera** en la fabricación de muebles.

Para instalar y usar la aplicación, ver el [README principal](../README.md). Esta carpeta contiene el análisis, la arquitectura y la planificación por sprints. Cada sprint es un documento independiente con objetivo, alcance, tareas, criterios de aceptación y entregables verificables.

## Índice

### Análisis y diseño
| Documento | Contenido |
|-----------|-----------|
| [00-vision-y-requisitos.md](00-vision-y-requisitos.md) | Visión, alcance, requisitos funcionales y no funcionales, prioridades |
| [01-arquitectura.md](01-arquitectura.md) | Capas, estructura de carpetas, flujo de datos, decisiones (ADR) |
| [02-modelo-de-dominio-y-datos.md](02-modelo-de-dominio-y-datos.md) | Entidades, esquema SQLite, repositorios |
| [03-algoritmo-de-optimizacion.md](03-algoritmo-de-optimizacion.md) | Bin packing 2D, MaxRects, Guillotine, estrategias, scoring |
| [04-plan-de-corte-fisico.md](04-plan-de-corte-fisico.md) | Kerf, márgenes, veta, tolerancias, secuencia de cortes, retazos |
| [05-interfaz-de-usuario.md](05-interfaz-de-usuario.md) | Layout, widgets, flujo de usuario, visualización, colores |
| [06-estrategia-de-testing.md](06-estrategia-de-testing.md) | Pirámide de tests, casos obligatorios, propiedades invariantes |
| [07-riesgos-y-problemas-conocidos.md](07-riesgos-y-problemas-conocidos.md) | Análisis previo de problemas del algoritmo y del entorno |
| [08-roadmap-futuro.md](08-roadmap-futuro.md) | Generador de muebles, costos, CNC/DXF/SVG, inventario avanzado |
| [benchmarks.md](benchmarks.md) | Rendimiento y calidad del optimizador (generado por `scripts/benchmark.py`) |
| [glosario.md](glosario.md) | Términos de taller y técnicos |

### Sprints
| Sprint | Documento | Objetivo |
|--------|-----------|----------|
| 0 | [sprint-00-fundaciones.md](sprints/sprint-00-fundaciones.md) | Entorno, estructura, utilidades de unidades y geometría |
| 1 | [sprint-01-dominio-y-persistencia.md](sprints/sprint-01-dominio-y-persistencia.md) | Modelos de dominio, SQLite, repositorios, datos semilla |
| 2 | [sprint-02-motor-de-optimizacion.md](sprints/sprint-02-motor-de-optimizacion.md) | Algoritmo de packing con kerf, margen, veta y multi-estrategia |
| 3 | [sprint-03-plan-de-corte-y-retazos.md](sprints/sprint-03-plan-de-corte-y-retazos.md) | Secuencia de cortes guillotina, clasificación de retazos |
| 4 | [sprint-04-interfaz-base.md](sprints/sprint-04-interfaz-base.md) | Ventana principal, placas, piezas, parámetros, proyectos |
| 5 | [sprint-05-visualizacion-y-resultados.md](sprints/sprint-05-visualizacion-y-resultados.md) | Diagrama de placas, leyenda, resumen, lista de cortes |
| 6 | [sprint-06-exportacion-inventario-retazos.md](sprints/sprint-06-exportacion-inventario-retazos.md) | PDF, CSV, inventario de placas, retazos reutilizables |
| 7 | [sprint-07-validacion-pulido-y-entrega.md](sprints/sprint-07-validacion-pulido-y-entrega.md) | Validaciones, demo, prueba E2E, README final, bases de costos |

## Convenciones

- **Idioma**: documentación y UI en español; identificadores de código en inglés salvo los nombres de módulos que el cliente solicitó (`placa.py`, `pieza.py`, ...).
- **Unidades**: todo en **milímetros** en el dominio. Ver [ADR-002](01-arquitectura.md#adr-002--representación-numérica-de-las-dimensiones).
- **Definición de Hecho (DoD)** común a todos los sprints:
  1. Código con type hints y docstrings en las funciones públicas.
  2. `pytest` en verde (sin tests saltados sin justificar).
  3. Los invariantes geométricos (sin solapes, dentro de la placa, kerf respetado) se verifican automáticamente.
  4. Documentación del sprint actualizada con lo realmente entregado (sección *Resultado*).
  5. `python app.py` arranca sin errores a partir del sprint 4.

## Orden de prioridades (del cliente)

1. Exactitud de dimensiones → 2. Sin superposición → 3. Sin exceder la placa → 4. Kerf → 5. Rotación/veta → 6. Mínimo de placas → 7. Mínimo desperdicio → 8. Menos cortes → 9. Visualización → 10. Estética.

> Si hay conflicto entre una interfaz bonita y un algoritmo correcto, **gana el algoritmo**.
