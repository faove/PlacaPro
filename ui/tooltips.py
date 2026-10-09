"""Textos de ayuda (tooltips) de los parámetros de corte. Fuente única para que la
explicación sea la misma en todos los paneles."""

from __future__ import annotations

KERF = (
    "<b>Kerf</b>: ancho del corte de la sierra (material que se pierde en cada corte).<br>"
    "Se descuenta solo <i>entre</i> piezas, no contra el borde de la placa.<br>"
    "Ej.: con margen 10 y kerf 3,2, una pieza de 500 mm va en x = 10 y la siguiente "
    "en x = 10 + 500 + 3,2 = 513,2."
)
EDGE_MARGIN = (
    "<b>Margen de refilado</b>: franja que se descarta en cada borde de la placa porque "
    "suele venir dañada o fuera de escuadra.<br>"
    "Con 10 mm, una placa de 1830 × 2820 deja 1810 × 2800 útiles."
)
EXTRA_SPACING = (
    "<b>Separación adicional</b>: holgura extra entre piezas, además del kerf "
    "(p. ej. para repasar cantos). Normalmente 0."
)
ROTATION = (
    "Permite girar 90° las piezas <b>sin veta</b>. Las piezas con veta se orientan según "
    "la veta de la placa, independientemente de esta opción."
)
PIECE_GRAIN = (
    "<b>Veta</b> de la pieza, referida a sus propias medidas:<br>"
    "• <i>Vertical</i>: la veta corre a lo largo del alto.<br>"
    "• <i>Horizontal</i>: la veta corre a lo largo del ancho.<br>"
    "• <i>Indiferente</i>: la pieza puede girarse libremente.<br>"
    "Si la placa tiene veta, la pieza se gira lo necesario para alinearlas."
)
PLATE_GRAIN = (
    "<b>Veta</b> de la placa: dirección de las fibras o del dibujo del laminado.<br>"
    "Sin veta, solo cuenta la veta (u orientación fija) de cada pieza."
)
LEVEL = (
    "Cuánto tiempo dedica el optimizador a buscar mejores combinaciones: "
    "<i>Rápida</i> (instantánea), <i>Equilibrada</i> o <i>Máxima</i> (más intentos)."
)
CUT_MODE = (
    "<i>Escuadradora</i>: cortes de guillotina de borde a borde, en etapas.<br>"
    "<i>CNC</i>: admite distribuciones no guillotinables (más densas); no genera "
    "secuencia de escuadradora."
)
MIN_OFFCUT = (
    "Un sobrante se considera <b>retazo reutilizable</b> si supera el ancho, el alto y el "
    "área mínimos; si no, cuenta como desperdicio."
)
