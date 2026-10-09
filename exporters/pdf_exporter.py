"""Informe PDF A4 para el taller (``QPdfWriter`` + ``QPainter``).

* Página 1: proyecto (datos, muebles, placa, parámetros de corte).
* Página 2: resumen de materiales (métricas, placas, retazos, despiece).
* Página 3..n: una placa por página: diagrama (el mismo ``SheetScene`` de la UI, con
  líneas de corte y cotas), piezas con X/Y/rotación y secuencia de cortes.
* Pie: proyecto y «Página i de N».

El documento se escribe a 96 ppp: así un «píxel» de la UI mide lo mismo en papel y los
textos del diagrama (tamaño fijo de pantalla) salen a ≈ 8 pt. Todo es vectorial.

Cada sección empieza en página nueva; las tablas largas continúan en páginas siguientes
(«(cont.)»), por eso un proyecto muy grande puede tener más de ``2 + nº de placas``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)

from exporters.base import ExportContext, register
from exporters.tables import (
    cut_list_table,
    percent,
    piece_list_table,
    sequence_table,
    sheet_summary_table,
    yes_no,
)
from models.parametros import CutMode
from models.resultado import SheetLayout
from models.retazo import OffcutStatus
from utils.constants import APP_NAME
from utils.units import format_area_m2, format_length

RESOLUTION = 96
PAGE_MARGIN = 40
FOOTER_HEIGHT = 24
BLOCK_GAP = 10
ROW_HEIGHT = 15
TABLE_FONT_PX = 10
TEXT_FONT_PX = 11
HEADER_BACKGROUND = "#E8EEF4"
RULE_COLOR = "#B0BEC5"
TEXT_COLOR = "#212121"
MUTED_COLOR = "#607D8B"
DIAGRAM_HEIGHT = 470


def _font(px: int, bold: bool = False) -> QFont:
    font = QFont()
    font.setPixelSize(px)
    font.setBold(bold)
    return font


# --------------------------------------------------------------------------- bloques


@dataclass
class Heading:
    text: str
    size: int = 15

    def height(self, width: float) -> float:
        return self.size * 1.7


@dataclass
class Paragraph:
    text: str
    color: str = TEXT_COLOR

    def height(self, width: float) -> float:
        metrics = QFontMetricsF(_font(TEXT_FONT_PX))
        flags = int(Qt.TextFlag.TextWordWrap)
        return metrics.boundingRect(QRectF(0, 0, width, 1e6), flags, self.text).height() + 4


@dataclass
class KeyValues:
    rows: list[tuple[str, str]]
    key_width: float = 200

    def height(self, width: float) -> float:
        return len(self.rows) * ROW_HEIGHT


@dataclass
class Table:
    title: str
    headers: list[str]
    rows: list[list[str]]
    widths: list[float]
    """Fracciones del ancho disponible (se normalizan)."""
    right: set[int] = field(default_factory=set)
    """Columnas alineadas a la derecha."""

    def fixed_height(self) -> float:
        return (Heading(self.title, 12).height(0) if self.title else 0) + ROW_HEIGHT

    def height(self, width: float) -> float:
        return self.fixed_height() + ROW_HEIGHT * len(self.rows)


@dataclass
class Diagram:
    sheet: SheetLayout
    ctx: ExportContext

    def height(self, width: float) -> float:
        return DIAGRAM_HEIGHT


@dataclass
class Legend:
    entries: list[tuple[str, str]]

    def lines(self, width: float) -> list[list[tuple[str, str]]]:
        metrics = QFontMetricsF(_font(TABLE_FONT_PX))
        lines: list[list[tuple[str, str]]] = [[]]
        used = 0.0
        for text, color in self.entries:
            w = metrics.horizontalAdvance(text) + 30
            if lines[-1] and used + w > width:
                lines.append([])
                used = 0
            lines[-1].append((text, color))
            used += w
        return lines

    def height(self, width: float) -> float:
        return len(self.lines(width)) * ROW_HEIGHT


Block = Heading | Paragraph | KeyValues | Table | Diagram | Legend


@dataclass
class Placed:
    block: Block
    y: float
    rows: tuple[int, int] | None = None
    """Tramo de filas de una tabla partida."""
    continued: bool = False


def paginate(
    sections: Sequence[Sequence[Block]], width: float, height: float
) -> list[list[Placed]]:
    """Reparte los bloques en páginas. Cada sección empieza en página nueva; las tablas se
    parten por filas y el resto de los bloques pasa entero a la página siguiente."""
    pages: list[list[Placed]] = []
    for section in sections:
        page: list[Placed] = []
        y = 0.0
        pages.append(page)
        for block in section:
            if isinstance(block, Table):
                start = 0
                continued = False
                while True:
                    room = height - y - block.fixed_height()
                    fit = int(room // ROW_HEIGHT) if room > 0 else 0
                    remaining = len(block.rows) - start
                    if fit < min(1, remaining) or (fit < remaining and fit < 3 and page):
                        page = []
                        pages.append(page)
                        y = 0.0
                        continue
                    take = min(fit, remaining)
                    page.append(Placed(block, y, (start, start + take), continued))
                    y += block.fixed_height() + take * ROW_HEIGHT + BLOCK_GAP
                    start += take
                    if start >= len(block.rows):
                        break
                    continued = True
                    page = []
                    pages.append(page)
                    y = 0.0
                continue
            h = block.height(width)
            if page and y + h > height:
                page = []
                pages.append(page)
                y = 0.0
            page.append(Placed(block, y))
            y += h + BLOCK_GAP
    return pages


# --------------------------------------------------------------------------- dibujo


class _Renderer:
    def __init__(self, painter: QPainter, content: QRectF) -> None:
        self.p = painter
        self.content = content

    def draw(self, placed: Placed) -> None:
        block = placed.block
        x, y, w = self.content.left(), self.content.top() + placed.y, self.content.width()
        if isinstance(block, Heading):
            self.p.setFont(_font(block.size, bold=True))
            self.p.setPen(QColor(TEXT_COLOR))
            self.p.drawText(
                QRectF(x, y, w, block.height(w)), Qt.AlignmentFlag.AlignVCenter, block.text
            )
        elif isinstance(block, Paragraph):
            self.p.setFont(_font(TEXT_FONT_PX))
            self.p.setPen(QColor(block.color))
            self.p.drawText(
                QRectF(x, y, w, block.height(w)), int(Qt.TextFlag.TextWordWrap), block.text
            )
        elif isinstance(block, KeyValues):
            self._key_values(block, x, y, w)
        elif isinstance(block, Table):
            self._table(block, placed, x, y, w)
        elif isinstance(block, Diagram):
            self._diagram(block, QRectF(x, y, w, DIAGRAM_HEIGHT))
        elif isinstance(block, Legend):
            self._legend(block, x, y, w)

    def _cell(self, rect: QRectF, text: str, font: QFont, right: bool = False) -> None:
        inner = rect.adjusted(3, 0, -3, 0)
        elided = QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, inner.width())
        align = Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft
        self.p.drawText(inner, align | Qt.AlignmentFlag.AlignVCenter, elided)

    def _key_values(self, block: KeyValues, x: float, y: float, w: float) -> None:
        key_font, value_font = _font(TEXT_FONT_PX), _font(TEXT_FONT_PX, bold=True)
        for i, (key, value) in enumerate(block.rows):
            top = y + i * ROW_HEIGHT
            self.p.setFont(key_font)
            self.p.setPen(QColor(MUTED_COLOR))
            self._cell(QRectF(x, top, block.key_width, ROW_HEIGHT), key, key_font)
            self.p.setFont(value_font)
            self.p.setPen(QColor(TEXT_COLOR))
            self._cell(
                QRectF(x + block.key_width, top, w - block.key_width, ROW_HEIGHT), value, value_font
            )

    def _table(self, block: Table, placed: Placed, x: float, y: float, w: float) -> None:
        if block.title:
            title = Heading(block.title + (" (cont.)" if placed.continued else ""), 12)
            self.draw(Placed(title, y - self.content.top()))
            y += title.height(w)
        total = sum(block.widths)
        widths = [w * f / total for f in block.widths]
        lefts = [x + sum(widths[:i]) for i in range(len(widths))]
        header_font, body_font = _font(TABLE_FONT_PX, bold=True), _font(TABLE_FONT_PX)
        self.p.fillRect(QRectF(x, y, w, ROW_HEIGHT), QColor(HEADER_BACKGROUND))
        self.p.setFont(header_font)
        self.p.setPen(QColor(TEXT_COLOR))
        for i, header in enumerate(block.headers):
            self._cell(
                QRectF(lefts[i], y, widths[i], ROW_HEIGHT), header, header_font, i in block.right
            )
        start, end = placed.rows or (0, len(block.rows))
        self.p.setFont(body_font)
        rule = QPen(QColor(RULE_COLOR), 0.5)
        for r, row in enumerate(block.rows[start:end]):
            top = y + ROW_HEIGHT * (r + 1)
            for i, text in enumerate(row):
                self._cell(
                    QRectF(lefts[i], top, widths[i], ROW_HEIGHT), text, body_font, i in block.right
                )
            self.p.setPen(rule)
            self.p.drawLine(
                QRectF(x, top, w, ROW_HEIGHT).bottomLeft(),
                QRectF(x, top, w, ROW_HEIGHT).bottomRight(),
            )
            self.p.setPen(QColor(TEXT_COLOR))

    def _diagram(self, block: Diagram, target: QRectF) -> None:
        # Importación diferida: el diagrama vive en la UI (mismo renderizado que en pantalla).
        from ui.cutting_diagram_widget import SheetScene
        from ui.units_display import UnitsDisplay

        units = UnitsDisplay(block.ctx.unit)
        scene = SheetScene(block.sheet, units)
        scene.set_cuts_visible(True)
        scene.set_dimensions_visible(True)
        self.p.save()
        self.p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(self.p, target, scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.p.restore()
        scene.deleteLater()
        units.deleteLater()

    def _legend(self, block: Legend, x: float, y: float, w: float) -> None:
        font = _font(TABLE_FONT_PX)
        self.p.setFont(font)
        metrics = QFontMetricsF(font)
        for n, line in enumerate(block.lines(w)):
            left = x
            top = y + n * ROW_HEIGHT
            for text, color in line:
                self.p.fillRect(QRectF(left, top + 3, 10, 10), QColor(color))
                self.p.setPen(QColor(TEXT_COLOR))
                self.p.drawText(
                    QRectF(left + 14, top, w, ROW_HEIGHT), Qt.AlignmentFlag.AlignVCenter, text
                )
                left += metrics.horizontalAdvance(text) + 30

    def footer(self, page_rect: QRectF, project_name: str, page: int, total: int) -> None:
        y = page_rect.bottom() - PAGE_MARGIN + 6
        rect = QRectF(self.content.left(), y, self.content.width(), FOOTER_HEIGHT - 6)
        self.p.setPen(QPen(QColor(RULE_COLOR), 0.5))
        self.p.drawLine(rect.topLeft(), rect.topRight())
        self.p.setFont(_font(TABLE_FONT_PX))
        self.p.setPen(QColor(MUTED_COLOR))
        self.p.drawText(
            rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{APP_NAME} · {project_name}",
        )
        self.p.drawText(
            rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"Página {page} de {total}",
        )


# --------------------------------------------------------------------------- contenido


def _date(ctx: ExportContext, value) -> str:  # type: ignore[no-untyped-def]
    if value is None:
        return "—"
    return value.astimezone().strftime("%d/%m/%Y %H:%M")


def project_section(ctx: ExportContext) -> list[Block]:
    project, result, plate, u = ctx.project, ctx.result, ctx.plate, ctx.unit
    params = result.params

    def length(v: int) -> str:
        return format_length(v, u, with_unit=True)

    blocks: list[Block] = [
        Heading(f"Plan de corte — {project.name}", 18),
        KeyValues(
            [
                ("Proyecto", project.name),
                ("Fecha del informe", ctx.generated_at.strftime("%d/%m/%Y %H:%M")),
                ("Fecha del cálculo", _date(ctx, result.created_at)),
                (
                    "Plan confirmado",
                    _date(ctx, result.confirmed_at) if result.is_confirmed else "No",
                ),
            ]
        ),
    ]
    if project.description:
        blocks.append(Paragraph(project.description))
    blocks.append(Heading("Muebles", 13))
    furniture_rows = []
    for item in project.furniture:
        specs = [s for name, s in ctx.pieces if name == item.name]
        count = sum(s.quantity for s in specs)
        furniture_rows.append((item.name, f"{len(specs)} piezas distintas · {count} en total"))
    blocks.append(KeyValues(furniture_rows or [("—", "Sin muebles")]))
    blocks.append(Heading("Placa", 13))
    if plate is not None:
        blocks.append(
            KeyValues(
                [
                    ("Nombre", plate.name),
                    (
                        "Medidas",
                        f"{format_length(plate.width, u)} × "
                        f"{format_length(plate.height, u)} {u.symbol}",
                    ),
                    ("Espesor", length(plate.thickness)),
                    ("Material", ctx.material_name(plate.material_id) or "—"),
                    ("Color", plate.color or "—"),
                    ("Veta", plate.grain.label),
                ]
            )
        )
    else:
        blocks.append(Paragraph("La placa del proyecto ya no existe."))
    blocks.append(Heading("Parámetros de corte", 13))
    blocks.append(
        KeyValues(
            [
                ("Espesor de sierra (kerf)", length(params.kerf)),
                ("Margen de refilado", length(params.edge_margin)),
                ("Separación extra", length(params.extra_spacing)),
                ("Rotación permitida", yes_no(params.allow_rotation)),
                ("Nivel de optimización", params.level.label),
                ("Máquina", params.cut_mode.label),
                ("Usar primero placas del inventario", yes_no(params.use_stock_first)),
                ("Usar primero retazos", yes_no(params.use_offcuts_first)),
                (
                    "Retazo mínimo",
                    f"{format_length(params.min_offcut_width, u)} × "
                    f"{format_length(params.min_offcut_height, u)} {u.symbol} · "
                    f"{format_area_m2(params.min_offcut_area)}",
                ),
            ],
            key_width=240,
        )
    )
    return blocks


def summary_section(ctx: ExportContext) -> list[Block]:
    r, u = ctx.result, ctx.unit
    blocks: list[Block] = [
        Heading("Resumen de materiales", 18),
        KeyValues(
            [
                ("Placas necesarias", str(r.sheets_count)),
                ("Área total", format_area_m2(r.total_area)),
                ("Área utilizada", format_area_m2(r.used_area)),
                ("Desperdicio", format_area_m2(r.waste_area)),
                ("Aprovechamiento", percent(r.utilization)),
                ("Piezas colocadas", str(r.pieces_count)),
                ("Retazos reutilizables", format_area_m2(r.reusable_offcut_area)),
                ("Cota inferior", f"{r.lower_bound} placa{'' if r.lower_bound == 1 else 's'}"),
                ("Estrategia", r.strategy or "—"),
            ]
        ),
    ]
    formats: dict[tuple[str, int, int], int] = {}
    for s in r.sheets:
        key = (s.source.label, s.width, s.height)
        formats[key] = formats.get(key, 0) + 1
    blocks.append(
        Table(
            "Placas por formato",
            ["Origen", f"Medidas ({u.symbol})", "Cantidad"],
            [
                [src, f"{format_length(w, u)} × {format_length(h, u)}", str(n)]
                for (src, w, h), n in formats.items()
            ],
            [2, 3, 1],
            {2},
        )
    )
    headers, rows = sheet_summary_table(ctx)
    blocks.append(
        Table("Placas", headers, rows, [0.7, 1.2, 2, 0.8, 1, 1.1, 1.3, 1.1], {0, 3, 4, 5, 6, 7})
    )
    offcuts = [
        (s, o)
        for s in r.sheets
        for o in s.offcuts
        if o.status in (OffcutStatus.REUSABLE, OffcutStatus.IN_STOCK)
    ]
    if offcuts:
        blocks.append(
            Table(
                "Retazos reutilizables",
                ["Retazo", "Placa", f"Medidas ({u.symbol})", "Área", "Estado"],
                [
                    [
                        o.label,
                        str(s.index + 1),
                        f"{format_length(o.width, u)} × {format_length(o.height, u)}",
                        format_area_m2(o.area),
                        o.status.label,
                    ]
                    for s, o in offcuts
                ],
                [1, 0.7, 2, 1.2, 1.6],
                {1, 3},
            )
        )
    if r.unplaced:
        blocks.append(Heading(f"Piezas no ubicadas ({len(r.unplaced)})", 13))
        blocks += [Paragraph(f"• {u_.reason}", "#C62828") for u_ in r.unplaced]
    headers, rows = piece_list_table(ctx)
    keep = [0, 1, 2, 3, 4, 5, 6, 7]
    blocks.append(
        Table(
            "Lista de piezas",
            [headers[i] for i in keep],
            [[row[i] for i in keep] for row in rows],
            [1.5, 1.5, 1, 0.9, 1, 1, 1.2, 1.5],
            {3, 4, 5, 6},
        )
    )
    return blocks


def sheet_section(ctx: ExportContext, sheet: SheetLayout) -> list[Block]:
    from ui.cutting_diagram_widget import legend_entries  # import diferido (UI)

    u = ctx.unit
    title = (
        f"Placa {sheet.index + 1} — {sheet.source.label} — "
        f"{format_length(sheet.width, u)} × {format_length(sheet.height, u)} {u.symbol} — "
        f"aprovechamiento {percent(sheet.utilization)}"
    )
    single = replace(ctx.result, sheets=(sheet,))
    blocks: list[Block] = [Heading(title, 15), Diagram(sheet, ctx), Legend(legend_entries(single))]
    headers, rows = cut_list_table(ctx, sheet)
    keep = [0, 1, 2, 3, 5, 6, 7]  # sin la columna Placa
    blocks.append(
        Table(
            "Piezas",
            [headers[i] for i in keep],
            [[row[i] for i in keep] for row in rows],
            [0.6, 3, 1, 1, 1, 1, 0.9],
            {0, 2, 3, 4, 5},
        )
    )
    if sheet.cut_plan is not None and sheet.cut_plan.mode is CutMode.CNC:
        blocks.append(Paragraph("Corte en CNC: la distribución no es guillotinable."))
    else:
        headers, rows = sequence_table(ctx, sheet)
        blocks.append(
            Table(
                "Secuencia de cortes",
                headers[1:],
                [row[1:] for row in rows],
                [0.6, 0.9, 1.2, 2, 1.4, 3.9],
                {0, 3, 4},
            )
        )
    return blocks


def build_sections(ctx: ExportContext) -> list[list[Block]]:
    return [
        project_section(ctx),
        summary_section(ctx),
        *(sheet_section(ctx, s) for s in ctx.result.sheets),
    ]


class PdfExporter:
    id = "pdf"
    name = "PDF (informe para el taller)…"
    file_filter = "PDF (*.pdf)"
    suffix = ".pdf"
    menu_order = 10

    def export(self, context: ExportContext, path: Path) -> list[Path]:
        path = Path(path)
        writer = QPdfWriter(str(path))
        writer.setResolution(RESOLUTION)
        writer.setPageLayout(
            QPageLayout(
                QPageSize(QPageSize.PageSizeId.A4),
                QPageLayout.Orientation.Portrait,
                QMarginsF(0, 0, 0, 0),
            )
        )
        writer.setTitle(f"{context.project.name} — plan de corte")
        writer.setCreator(APP_NAME)
        painter = QPainter(writer)
        try:
            page_rect = QRectF(0, 0, writer.width(), writer.height())
            content = page_rect.adjusted(
                PAGE_MARGIN, PAGE_MARGIN, -PAGE_MARGIN, -PAGE_MARGIN - FOOTER_HEIGHT
            )
            pages = paginate(build_sections(context), content.width(), content.height())
            renderer = _Renderer(painter, content)
            for i, page in enumerate(pages):
                if i:
                    writer.newPage()
                for placed in page:
                    renderer.draw(placed)
                renderer.footer(page_rect, context.project.name, i + 1, len(pages))
        finally:
            painter.end()
        return [path]


register(PdfExporter())
