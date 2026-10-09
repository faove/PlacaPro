# 08 — Roadmap futuro (post v1)

La v1 deja **interfaces, entidades y tablas** listas para lo siguiente, sin UI completa.

## 1. Generador automático de muebles
- Interfaz: `FurnitureGenerator.generate(dims: FurnitureDimensions, params: dict) -> list[PieceSpec]`.
- v1: `ManualGenerator` (devuelve las piezas cargadas a mano).
- v1 (experimental, sin UI): `DeskGenerator` en `services/furniture_generator.py` — tapa, 2 laterales y faldón a partir de `FurnitureDimensions`; no está registrado en `GENERATORS`. `tests/test_future_ready.py` recorre Dimensiones → Despiece → Piezas → Optimizador.
- **Pendiente al exponer generadores en la UI**: `validate_project` valida `furniture.pieces` (las piezas manuales); hay que validar el despiece generado (`OptimizationService.piece_specs`) y mapear los mensajes a campos del mueble en lugar de a filas de la tabla.
- Futuro: `DeskGenerator`, `NightstandGenerator`, `CabinetGenerator`, `WardrobeGenerator` basados en reglas:
  - Ejemplo escritorio 1400 × 750 × 600, espesor e = 18:
    - Laterales: 2 × (alto − e) × profundidad
    - Tapa: 1 × ancho × profundidad
    - Fondo / faldón: 1 × (ancho − 2e) × 300
    - Soportes: 2 × (ancho − 2e) × 100
  - Reglas configurables (tapa montada sobre / entre laterales, fondo encajado / clavado, holgura de puertas 2–3 mm, descuento de canto).
- Catálogo de muebles: plantillas guardadas en la tabla `furniture` con `generator_id` + `generator_params_json`.

## 2. Costos
- `MaterialCost`: precio por placa y por m²; costo de desperdicio = área desperdiciada × precio m².
- Herrajes (`hardware_items`, `furniture_hardware`), mano de obra (horas × tarifa), tapacantos (metros lineales por pieza).
- `CostService.compute(project, result, material_costs=None) -> CostBreakdown` con costo total, precio de venta y margen %. En v1 la firma está fijada por un test y lanza `NotImplementedError`; las tablas `hardware_items` y `furniture_hardware` ya existen.

## 3. Exportadores
| Formato | Uso | Notas |
|---------|-----|-------|
| SVG | Vista web / impresión | Reutiliza la geometría del layout |
| DXF | CAD / CNC | `ezdxf`; capas por pieza, retazo, corte |
| CNC / G-code | Router | Requiere herramienta, profundidad de pasada, tabs, orden de mecanizado |
| Escuadradora | Hoja de taller | Ya en v1 (PDF) |
| Etiquetas | Impresora térmica | Etiqueta por pieza con QR (proyecto, pieza, placa) |

## 4. Inventario y proveedores
- Movimientos de stock (entradas/salidas), reserva al confirmar un plan de corte.
- Proveedores con precios por formato; elegir formato de placa más económico para un proyecto (optimización multi-formato).

## 5. Optimización avanzada
- Multi-formato simultáneo (elegir la combinación de placas de distinto tamaño con menor costo).
- Multi-material en una corrida.
- Cantos / tapacantos con descuento de medida.
- Metaheurísticas (algoritmo genético sobre secuencia + heurística, simulated annealing).
- Paralelismo por procesos.

## 6. Plataforma
- CLI (`python -m placapro optimize proyecto.json`).
- API local / versión web reutilizando el núcleo (sin Qt).
