"""Resumen del resultado (provisional, en texto). El sprint 5 añade KPIs y tabla."""

from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QTextBrowser, QWidget

from models.resultado import OptimizationResult
from ui.theme import ERROR_COLOR
from ui.units_display import UnitsDisplay
from utils.units import format_area_m2


def result_summary_html(result: OptimizationResult, units: UnitsDisplay) -> str:
    rows = [
        ("Placas", str(result.sheets_count)),
        ("Área total", format_area_m2(result.total_area)),
        ("Utilizada", format_area_m2(result.used_area)),
        ("Desperdicio", format_area_m2(result.waste_area)),
        ("Retazos reutilizables", format_area_m2(result.reusable_offcut_area)),
        ("Aprovechamiento", f"{result.utilization * 100:.1f} %".replace(".", ",")),
        ("Piezas ubicadas", str(result.pieces_count)),
        ("Estrategia", escape(result.strategy)),
        ("Tiempo", f"{result.duration_ms} ms"),
    ]
    parts = ["<h3>RESULTADO</h3><table cellspacing='4'>"]
    parts += [f"<tr><td>{k}</td><td align='right'><b>{v}</b></td></tr>" for k, v in rows]
    parts.append("</table><h4>PLACAS</h4><table cellspacing='4'>")
    for sheet in result.sheets:
        dims = f"{units.format(sheet.width)} × {units.format(sheet.height)} {units.symbol}"
        parts.append(
            f"<tr><td>Placa {sheet.index + 1}</td><td>{sheet.source.label}</td>"
            f"<td>{dims}</td><td align='right'>{sheet.utilization * 100:.1f} %</td>"
            f"<td align='right'>{len(sheet.placements)} piezas</td></tr>".replace(".", ",")
        )
    parts.append("</table>")
    if result.unplaced:
        parts.append(
            f"<h4 style='color:{ERROR_COLOR}'>PIEZAS NO UBICADAS ({len(result.unplaced)})</h4><ul>"
        )
        parts += [f"<li>{escape(u.reason)}</li>" for u in result.unplaced]
        parts.append("</ul>")
    return "".join(parts)


class ResultWidget(QTextBrowser):
    def __init__(self, units: UnitsDisplay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.units = units
        self.result: OptimizationResult | None = None
        units.unit_changed.connect(lambda _unit: self.set_result(self.result))
        self.set_result(None)

    def set_result(self, result: OptimizationResult | None) -> None:
        self.result = result
        if result is None:
            self.setHtml("<h3>RESULTADO</h3><p>Pulse <b>OPTIMIZAR CORTES</b> para calcular.</p>")
        else:
            self.setHtml(result_summary_html(result, self.units))

    def set_message(self, html: str) -> None:
        self.result = None
        self.setHtml(html)
