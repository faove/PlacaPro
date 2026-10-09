"""Tablas de texto comunes a los exportadores (mismas columnas que la UI).

Las longitudes se escriben en la unidad del contexto, sin unidad (va en el encabezado) y
con coma decimal.
"""

from __future__ import annotations

from exporters.base import ExportContext
from models.plan_corte import CutOrientation
from models.resultado import SheetLayout
from utils.units import format_area_m2, format_length

ORIENTATION_LABELS = {CutOrientation.HORIZONTAL: "Horizontal", CutOrientation.VERTICAL: "Vertical"}


def percent(fraction: float) -> str:
    return f"{fraction * 100:.1f} %".replace(".", ",")


def yes_no(value: bool) -> str:
    return "Sí" if value else "No"


def _len(ctx: ExportContext, value: int) -> str:
    return format_length(value, ctx.unit)


def piece_list_table(ctx: ExportContext) -> tuple[list[str], list[list[str]]]:
    """Despiece del proyecto (una fila por pieza definida, con su cantidad)."""
    u = ctx.unit.symbol
    headers = [
        "Mueble",
        "Pieza",
        "Categoría",
        "Cantidad",
        f"Ancho ({u})",
        f"Alto ({u})",
        f"Espesor ({u})",
        "Material",
        "Rotación",
        "Veta",
        "Orientación fija",
        "Notas",
    ]
    rows = [
        [
            furniture,
            spec.name,
            spec.category.label,
            str(spec.quantity),
            _len(ctx, spec.width),
            _len(ctx, spec.height),
            _len(ctx, spec.thickness),
            ctx.material_name(spec.material_id),
            yes_no(spec.can_rotate),
            spec.grain.label,
            yes_no(spec.fixed_orientation),
            spec.notes,
        ]
        for furniture, spec in ctx.pieces
    ]
    return headers, rows


def cut_list_table(
    ctx: ExportContext, sheet: SheetLayout | None = None
) -> tuple[list[str], list[list[str]]]:
    """Lista de cortes: una fila por pieza colocada (de todas las placas o de una)."""
    u = ctx.unit.symbol
    headers = [
        "Nº",
        "Pieza",
        f"Ancho ({u})",
        f"Alto ({u})",
        "Placa",
        f"X ({u})",
        f"Y ({u})",
        "Rotación",
    ]
    rows: list[list[str]] = []
    number = 0
    for s in ctx.result.sheets:
        for p in s.placements:
            number += 1
            if sheet is not None and s.index != sheet.index:
                continue
            rows.append(
                [
                    str(number),
                    p.piece.label,
                    _len(ctx, p.width),
                    _len(ctx, p.height),
                    str(s.index + 1),
                    _len(ctx, p.x),
                    _len(ctx, p.y),
                    yes_no(p.rotated),
                ]
            )
    return headers, rows


def sequence_table(
    ctx: ExportContext, sheet: SheetLayout | None = None
) -> tuple[list[str], list[list[str]]]:
    """Secuencia de cortes de escuadradora (de todas las placas o de una)."""
    u = ctx.unit.symbol
    headers = [
        "Placa",
        "Corte",
        "Nivel",
        "Orientación",
        f"Medida de tope ({u})",
        f"Longitud ({u})",
        "Resultado",
    ]
    rows: list[list[str]] = []
    for s in ctx.result.sheets if sheet is None else (sheet,):
        for c in s.cut_plan.cuts if s.cut_plan else ():
            rows.append(
                [
                    str(s.index + 1),
                    str(c.order),
                    "0 (refilado)" if c.is_trim else str(c.level),
                    ORIENTATION_LABELS[c.orientation],
                    _len(ctx, c.fence_distance),
                    _len(ctx, c.length),
                    ", ".join(c.resulting_labels(ctx.unit)),
                ]
            )
    return headers, rows


def sheet_summary_table(ctx: ExportContext) -> tuple[list[str], list[list[str]]]:
    u = ctx.unit.symbol
    headers = [
        "Placa",
        "Origen",
        f"Medidas ({u})",
        "Piezas",
        "Aprov.",
        "Usada",
        "Desperdicio",
        "Retazos",
    ]
    rows = [
        [
            str(s.index + 1),
            s.source.label,
            f"{_len(ctx, s.width)} × {_len(ctx, s.height)}",
            str(len(s.placements)),
            percent(s.utilization),
            format_area_m2(s.used_area),
            format_area_m2(s.waste_area),
            format_area_m2(s.reusable_offcut_area),
        ]
        for s in ctx.result.sheets
    ]
    return headers, rows
