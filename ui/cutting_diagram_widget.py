"""Diagrama a escala de cada placa del resultado (``QGraphicsScene``).

Regla de oro (docs/05-interfaz-de-usuario.md §3): la escena se construye **solo** desde
un ``SheetLayout``. Cada rectángulo dibujado es la placa, una ``Placement`` o un
``Offcut`` (retazo o desperdicio); las líneas de corte salen del ``CutPlan``.

Escala: 1 unidad de escena = 1 unidad interna (0,1 mm). Así los rectángulos de la escena
coinciden **exactamente** con las coordenadas enteras del modelo (ADR-002), sin pasar
por ``float`` con décimas. Origen arriba-izquierda, eje Y hacia abajo (como el taller y Qt).

Los textos se pintan en coordenadas de pantalla con un tamaño fijo y se recortan al
rectángulo que etiquetan: son legibles con cualquier zoom y nunca invaden otra pieza.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QStyleOptionGraphicsItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from models.pieza import GrainDirection, PieceCategory
from models.plan_corte import Cut, CutOrientation
from models.resultado import OptimizationResult, Placement, SheetLayout
from models.retazo import Offcut, OffcutStatus
from ui.theme import (
    CATEGORY_COLORS,
    CUT_LINE_COLOR,
    DIMENSION_COLOR,
    MARGIN_COLOR,
    OFFCUT_COLOR,
    PLATE_BORDER_COLOR,
    PLATE_COLOR,
    SELECTION_COLOR,
    WASTE_COLOR,
    text_color_for,
)
from ui.units_display import UnitsDisplay
from utils.units import INTERNAL_PER_MM

LABEL_FONT_PX = 11
LABEL_PADDING_PX = 3
DIMENSION_OFFSET = 120 * INTERNAL_PER_MM
"""Distancia de las cotas al borde de la placa (unidades de escena)."""
ZOOM_STEP = 1.15
MIN_SCALE, MAX_SCALE = 0.002, 2.0

REUSABLE_STATUSES = (OffcutStatus.REUSABLE, OffcutStatus.IN_STOCK)
ROTATED_MARK = "⟲"
GRAIN_MARKS = {CutOrientation.VERTICAL: "↕", CutOrientation.HORIZONTAL: "↔"}


def percent_label(fraction: float) -> str:
    return f"{fraction * 100:.1f} %".replace(".", ",")


def sheet_tab_title(sheet: SheetLayout) -> str:
    return f"Placa {sheet.index + 1} — {percent_label(sheet.utilization)}"


def grain_on_sheet(placement: Placement) -> CutOrientation | None:
    """Dirección de la veta de la pieza ya colocada (girada si la pieza está rotada).

    Se expresa como orientación de línea: ``VERTICAL`` = veta paralela al eje Y.
    """
    grain = placement.piece.spec.grain
    if grain is GrainDirection.NONE:
        return None
    vertical = grain is GrainDirection.VERTICAL
    if placement.rotated:
        vertical = not vertical
    return CutOrientation.VERTICAL if vertical else CutOrientation.HORIZONTAL


def legend_entries(result: OptimizationResult | None) -> list[tuple[str, str]]:
    """(texto, color) de la leyenda: categorías presentes (en el orden de la paleta),
    retazo reutilizable y desperdicio si aparecen."""
    if result is None:
        return []
    present = {p.piece.spec.category for p in result.placements}
    entries: list[tuple[str, str]] = []
    seen_colors: dict[str, int] = {}
    for category, color in CATEGORY_COLORS.items():
        if category not in present:
            continue
        if color in seen_colors:  # Tapa y Base comparten color: una sola entrada
            i = seen_colors[color]
            entries[i] = (f"{entries[i][0]} / {category.label}", color)
            continue
        seen_colors[color] = len(entries)
        entries.append((category.label, color))
    offcuts = [o for s in result.sheets for o in s.offcuts]
    if any(o.status in REUSABLE_STATUSES for o in offcuts):
        entries.append(("Retazo reutilizable", OFFCUT_COLOR))
    if any(o.status is OffcutStatus.WASTE for o in offcuts):
        entries.append(("Desperdicio", WASTE_COLOR))
    return entries


def _cosmetic_pen(color: QColor | str, width: float = 1.0) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCosmetic(True)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    return pen


def _label_font() -> QFont:
    font = QFont()
    font.setPixelSize(LABEL_FONT_PX)
    return font


def draw_screen_text(
    painter: QPainter, rect: QRectF, lines: list[str], color: QColor, *, bold_first: bool = True
) -> None:
    """Escribe ``lines`` centradas en ``rect`` a tamaño fijo de pantalla.

    Se descartan las líneas que no caben en alto y se recortan («…») las que no caben en
    ancho; si el rectángulo es demasiado chico no se escribe nada.
    """
    device = painter.worldTransform().mapRect(rect)
    area = device.adjusted(LABEL_PADDING_PX, LABEL_PADDING_PX, -LABEL_PADDING_PX, -LABEL_PADDING_PX)
    font = _label_font()
    bold = QFont(font)
    bold.setBold(bold_first)
    metrics = QFontMetricsF(bold)
    line_height = metrics.height()
    fit = int(area.height() // line_height) if area.height() > 0 else 0
    lines = [line for line in lines if line][:fit]
    if not lines or area.width() < metrics.horizontalAdvance("M…"):
        return
    painter.save()
    painter.resetTransform()
    painter.setPen(color)
    top = area.center().y() - line_height * len(lines) / 2
    for i, line in enumerate(lines):
        f = bold if i == 0 else font
        text = QFontMetricsF(f).elidedText(line, Qt.TextElideMode.ElideRight, area.width())
        if text in ("", "…"):
            continue
        painter.setFont(f)
        line_rect = QRectF(area.left(), top + i * line_height, area.width(), line_height)
        painter.drawText(line_rect, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()


class PieceItem(QGraphicsRectItem):
    """Una ``Placement``: relleno por categoría, nombre, medidas, ⟲ si está rotada y flecha
    de veta. Seleccionable."""

    def __init__(self, placement: Placement, placement_index: int, units: UnitsDisplay) -> None:
        super().__init__(placement.x, placement.y, placement.width, placement.height)
        self.placement = placement
        self.placement_index = placement_index
        self.units = units
        self.fill = QColor(CATEGORY_COLORS[placement.piece.spec.category])
        self.setBrush(self.fill)
        self.setPen(_cosmetic_pen(self.fill.darker(160)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(2)
        self.refresh_texts()

    @property
    def category(self) -> PieceCategory:
        return self.placement.piece.spec.category

    def lines(self) -> list[str]:
        p = self.placement
        marks = []
        if p.rotated:
            marks.append(ROTATED_MARK)
        grain = grain_on_sheet(p)
        if grain is not None:
            marks.append(GRAIN_MARKS[grain])
        title = " ".join([p.piece.label, *marks])
        u = self.units
        return [title, f"{u.format(p.width)} × {u.format(p.height)}"]

    def refresh_texts(self) -> None:
        p = self.placement
        u = self.units
        rotation = "sí" if p.rotated else "no"
        spec = p.piece.spec
        self.setToolTip(
            f"<b>{p.piece.label}</b> ({spec.category.label})<br>"
            f"X = {u.format(p.x, with_unit=True)} · Y = {u.format(p.y, with_unit=True)}<br>"
            f"{u.format(p.width)} × {u.format(p.height)} {u.symbol} · rotada: {rotation}<br>"
            f"{spec.grain.label}"
        )
        self.update()

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        rect = self.rect()
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRect(rect)
        if self.isSelected():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(_cosmetic_pen(SELECTION_COLOR, 3))
            painter.drawRect(rect)
        draw_screen_text(painter, rect, self.lines(), text_color_for(self.fill))


class OffcutItem(QGraphicsRectItem):
    """Un ``Offcut``: retazo reutilizable (verde rayado + etiqueta) o desperdicio (gris)."""

    def __init__(self, offcut: Offcut, units: UnitsDisplay) -> None:
        assert offcut.x is not None and offcut.y is not None
        super().__init__(offcut.x, offcut.y, offcut.width, offcut.height)
        self.offcut = offcut
        self.units = units
        self.reusable = offcut.status in REUSABLE_STATUSES
        self.fill = QColor(OFFCUT_COLOR if self.reusable else WASTE_COLOR)
        self.setBrush(self.fill)
        self.setPen(
            _cosmetic_pen(self.fill.darker(140) if self.reusable else Qt.GlobalColor.transparent)
        )
        self.setZValue(1)
        self.refresh_texts()

    def lines(self) -> list[str]:
        if not self.reusable:
            return []
        o = self.offcut
        name = f"Retazo {o.label}" if o.label else "Retazo"
        return [name, f"{self.units.format(o.width)} × {self.units.format(o.height)}"]

    def refresh_texts(self) -> None:
        o = self.offcut
        u = self.units
        self.setToolTip(
            f"<b>{o.status.label}</b> {o.label}<br>"
            f"X = {u.format(o.x or 0, with_unit=True)} · Y = {u.format(o.y or 0, with_unit=True)}"
            f"<br>{u.format(o.width)} × {u.format(o.height)} {u.symbol}"
        )
        self.update()

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        rect = self.rect()
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRect(rect)
        if self.reusable:
            # Rayado diagonal en espaciado de pantalla (igual con cualquier zoom).
            painter.save()
            device = painter.worldTransform().mapRect(rect)
            painter.resetTransform()
            hatch = QBrush(self.fill.darker(130), Qt.BrushStyle.BDiagPattern)
            painter.setBrush(hatch)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(device)
            painter.restore()
            draw_screen_text(painter, rect, self.lines(), QColor("#1B5E20"))


class CutLineItem(QGraphicsRectItem):
    """Un ``Cut`` del plan: la franja de kerf, con una línea y el número de corte."""

    def __init__(self, cut: Cut, units: UnitsDisplay) -> None:
        if cut.orientation is CutOrientation.HORIZONTAL:
            rect = QRectF(cut.start, cut.position, cut.length, cut.kerf)
        else:
            rect = QRectF(cut.position, cut.start, cut.kerf, cut.length)
        super().__init__(rect)
        self.cut = cut
        self.units = units
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(3)
        self.refresh_texts()

    def refresh_texts(self) -> None:
        c = self.cut
        u = self.units
        kind = "refilado" if c.is_trim else f"nivel {c.level}"
        self.setToolTip(
            f"<b>CORTE {c.order}</b> ({kind}, {c.orientation.value})<br>"
            f"Tope: {u.format(c.fence_distance, with_unit=True)} · "
            f"Longitud: {u.format(c.length, with_unit=True)}"
        )
        self.update()

    def shape(self) -> QPainterPath:
        # Zona de clic algo más ancha que el kerf para poder seleccionar la línea.
        path = QPainterPath()
        grow = 5 * INTERNAL_PER_MM
        path.addRect(self.rect().adjusted(-grow, -grow, grow, grow))
        return path

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self.shape().boundingRect()

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        rect = self.rect()
        selected = self.isSelected()
        color = QColor(SELECTION_COLOR if selected else CUT_LINE_COLOR)
        pen = _cosmetic_pen(color, 3 if selected else 1.5)
        if self.cut.is_trim:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        center = rect.center()
        if self.cut.orientation is CutOrientation.HORIZONTAL:
            painter.drawLine(QPointF(rect.left(), center.y()), QPointF(rect.right(), center.y()))
            anchor = QPointF(rect.left(), center.y())
        else:
            painter.drawLine(QPointF(center.x(), rect.top()), QPointF(center.x(), rect.bottom()))
            anchor = QPointF(center.x(), rect.top())
        # Número del corte en un círculo de tamaño fijo junto al inicio del corte.
        point = painter.worldTransform().map(anchor)
        painter.save()
        painter.resetTransform()
        font = _label_font()
        font.setBold(True)
        painter.setFont(font)
        text = str(self.cut.order)
        radius = QFontMetricsF(font).horizontalAdvance(text) / 2 + 4
        if self.cut.orientation is CutOrientation.HORIZONTAL:
            point += QPointF(radius + 2, 0)
        else:
            point += QPointF(0, radius + 2)
        bubble = QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(bubble)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class DimensionItem(QGraphicsItem):
    """Cota de un borde de la placa: línea con topes y la medida en la unidad visible."""

    def __init__(self, start: QPointF, end: QPointF, value: int, units: UnitsDisplay) -> None:
        super().__init__()
        self.start, self.end, self.value, self.units = start, end, value, units
        self.setZValue(4)

    def boundingRect(self) -> QRectF:  # noqa: N802
        grow = DIMENSION_OFFSET / 2
        return QRectF(self.start, self.end).normalized().adjusted(-grow, -grow, grow, grow)

    def refresh_texts(self) -> None:
        self.update()

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        painter.setPen(_cosmetic_pen(DIMENSION_COLOR))
        painter.drawLine(self.start, self.end)
        horizontal = self.start.y() == self.end.y()
        tick = DIMENSION_OFFSET / 4
        for p in (self.start, self.end):
            if horizontal:
                painter.drawLine(QPointF(p.x(), p.y() - tick), QPointF(p.x(), p.y() + tick))
            else:
                painter.drawLine(QPointF(p.x() - tick, p.y()), QPointF(p.x() + tick, p.y()))
        a = painter.worldTransform().map(self.start)
        b = painter.worldTransform().map(self.end)
        mid = (a + b) / 2
        text = self.units.format(self.value, with_unit=True)
        painter.save()
        painter.resetTransform()
        font = _label_font()
        painter.setFont(font)
        width = QFontMetricsF(font).horizontalAdvance(text) + 6
        height = QFontMetricsF(font).height()
        painter.translate(mid)
        if not horizontal:
            painter.rotate(-90)
        box = QRectF(-width / 2, -height / 2, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PLATE_COLOR))
        painter.drawRect(box)
        painter.setPen(QColor(DIMENSION_COLOR))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class SheetScene(QGraphicsScene):
    """Escena de una placa, construida solo a partir de ``SheetLayout``."""

    def __init__(self, sheet: SheetLayout, units: UnitsDisplay, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.sheet = sheet
        self.units = units
        pad = DIMENSION_OFFSET * 2
        self.setSceneRect(QRectF(-pad, -pad, sheet.width + 2 * pad, sheet.height + 2 * pad))

        self.plate_item = self.addRect(
            QRectF(0, 0, sheet.width, sheet.height),
            _cosmetic_pen(PLATE_BORDER_COLOR, 2),
            QBrush(QColor(PLATE_COLOR)),
        )
        self.plate_item.setZValue(0)
        self.margin_item: QGraphicsPathItem | None = None
        m = sheet.edge_margin
        if m > 0:
            band = QPainterPath()
            band.addRect(QRectF(0, 0, sheet.width, sheet.height))
            band.addRect(QRectF(m, m, sheet.width - 2 * m, sheet.height - 2 * m))
            band.setFillRule(Qt.FillRule.OddEvenFill)
            self.margin_item = self.addPath(
                band,
                QPen(Qt.PenStyle.NoPen),
                QBrush(QColor(MARGIN_COLOR), Qt.BrushStyle.Dense5Pattern),
            )
            self.margin_item.setZValue(0.5)
            self.margin_item.setToolTip(f"Margen de refilado: {units.format(m, with_unit=True)}")

        self.piece_items = [PieceItem(p, i, units) for i, p in enumerate(sheet.placements)]
        self.offcut_items = [
            OffcutItem(o, units) for o in sheet.offcuts if o.x is not None and o.y is not None
        ]
        cuts = sheet.cut_plan.cuts if sheet.cut_plan else ()
        self.cut_items = {c.order: CutLineItem(c, units) for c in cuts}
        w, h = float(sheet.width), float(sheet.height)
        d = DIMENSION_OFFSET
        self.dimension_items = [
            DimensionItem(QPointF(0, -d), QPointF(w, -d), sheet.width, units),
            DimensionItem(QPointF(-d, 0), QPointF(-d, h), sheet.height, units),
        ]
        for item in (*self.offcut_items, *self.piece_items):
            self.addItem(item)
        for item in (*self.cut_items.values(), *self.dimension_items):
            item.setVisible(False)
            self.addItem(item)

    def set_cuts_visible(self, visible: bool) -> None:
        for item in self.cut_items.values():
            item.setVisible(visible)
            if not visible:
                item.setSelected(False)

    def set_dimensions_visible(self, visible: bool) -> None:
        for item in self.dimension_items:
            item.setVisible(visible)

    def refresh_units(self) -> None:
        if self.margin_item is not None:
            margin = self.units.format(self.sheet.edge_margin, with_unit=True)
            self.margin_item.setToolTip(f"Margen de refilado: {margin}")
        for item in (
            *self.piece_items,
            *self.offcut_items,
            *self.cut_items.values(),
            *self.dimension_items,
        ):
            item.refresh_texts()


class SheetView(QGraphicsView):
    """Zoom con la rueda (bajo el cursor), pan arrastrando y «ajustar a ventana».

    Mientras el usuario no haga zoom, la vista se reajusta sola al cambiar de tamaño.
    """

    def __init__(self, scene: SheetScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.auto_fit = True

    @property
    def sheet_scene(self) -> SheetScene:
        scene = self.scene()
        assert isinstance(scene, SheetScene)
        return scene

    def current_scale(self) -> float:
        return self.transform().m11()

    def fit_to_window(self) -> None:
        self.auto_fit = True
        self.fitInView(self.sheet_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        target = self.current_scale() * factor
        if target < MIN_SCALE or target > MAX_SCALE:
            return
        self.auto_fit = False
        self.scale(factor, factor)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        steps = event.angleDelta().y() / 120
        if steps:
            self.zoom(ZOOM_STEP**steps)
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.auto_fit:
            self.fit_to_window()


class CuttingDiagramWidget(QWidget):
    """Una pestaña por placa + leyenda + capas opcionales (cortes, cotas).

    Emite ``piece_selected(sheet_index, placement_index)`` y
    ``cut_selected(sheet_index, cut_order)`` cuando el usuario selecciona en el diagrama.
    """

    piece_selected = Signal(int, int)
    cut_selected = Signal(int, int)

    def __init__(self, units: UnitsDisplay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.units = units
        self.result: OptimizationResult | None = None
        self.views: list[SheetView] = []
        self._syncing = False

        self.stale_banner = QLabel(
            "⚠ Resultado desactualizado: los datos del proyecto cambiaron desde el cálculo. "
            "Pulse OPTIMIZAR CORTES para recalcular."
        )
        self.stale_banner.setObjectName("staleBanner")
        self.stale_banner.setWordWrap(True)
        self.stale_banner.hide()

        self.cuts_check = QCheckBox("Líneas de corte")
        self.dimensions_check = QCheckBox("Cotas")
        self.zoom_out_button = QPushButton("−")
        self.zoom_in_button = QPushButton("+")
        self.fit_button = QPushButton("Ajustar a ventana")
        for button in (self.zoom_out_button, self.zoom_in_button):
            button.setFixedWidth(32)
        self.zoom_in_button.setToolTip("Acercar (rueda del ratón)")
        self.zoom_out_button.setToolTip("Alejar (rueda del ratón)")
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.cuts_check)
        toolbar.addWidget(self.dimensions_check)
        toolbar.addStretch(1)
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(self.zoom_in_button)
        toolbar.addWidget(self.fit_button)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.placeholder = QLabel("El diagrama de las placas se mostrará aquí.")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.tabs)
        self.stack.setMinimumHeight(200)

        self.legend = QLabel()
        self.legend.setWordWrap(True)
        self.legend.setTextFormat(Qt.TextFormat.RichText)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stale_banner)
        layout.addLayout(toolbar)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.legend)

        self.cuts_check.toggled.connect(self._apply_layers)
        self.dimensions_check.toggled.connect(self._apply_layers)
        self.fit_button.clicked.connect(self.fit_current)
        self.zoom_in_button.clicked.connect(lambda: self._zoom_current(ZOOM_STEP))
        self.zoom_out_button.clicked.connect(lambda: self._zoom_current(1 / ZOOM_STEP))
        units.unit_changed.connect(lambda _unit: self._refresh_units())
        self.set_result(None)

    # ------------------------------------------------------------------ contenido
    @property
    def scenes(self) -> list[SheetScene]:
        return [v.sheet_scene for v in self.views]

    def set_result(self, result: OptimizationResult | None) -> None:
        self.result = result
        self.tabs.clear()
        for view in self.views:
            view.sheet_scene.deleteLater()
            view.deleteLater()
        self.views = []
        has_sheets = result is not None and bool(result.sheets)
        self.stack.setCurrentWidget(self.tabs if has_sheets else self.placeholder)
        if result is not None and not result.sheets:
            self.placeholder.setText("El resultado no tiene placas.")
        else:
            self.placeholder.setText("El diagrama de las placas se mostrará aquí.")
        for sheet in result.sheets if result else ():
            scene = SheetScene(sheet, self.units, self)
            scene.selectionChanged.connect(lambda s=scene: self._on_scene_selection(s))
            view = SheetView(scene)
            self.views.append(view)
            self.tabs.addTab(view, sheet_tab_title(sheet))
        self._apply_layers()
        self._update_legend()
        self.set_stale(False)

    def set_stale(self, stale: bool) -> None:
        self.stale_banner.setVisible(stale and self.result is not None)

    def _update_legend(self) -> None:
        entries = legend_entries(self.result)
        if not entries:
            self.legend.setText("")
            return
        parts = [
            f"<span style='color:{color}; font-size:15px'>■</span>&nbsp;{text}"
            for text, color in entries
        ]
        note = (
            f"<span style='color:{DIMENSION_COLOR}'>· {ROTATED_MARK} rotada · ↕↔ veta · "
            "origen arriba-izquierda</span>"
        )
        self.legend.setText("&nbsp;&nbsp; ".join(parts) + "&nbsp;&nbsp; " + note)

    def _apply_layers(self) -> None:
        for scene in self.scenes:
            scene.set_cuts_visible(self.cuts_check.isChecked())
            scene.set_dimensions_visible(self.dimensions_check.isChecked())

    def _refresh_units(self) -> None:
        for scene in self.scenes:
            scene.refresh_units()

    # ------------------------------------------------------------------ vista
    def current_view(self) -> SheetView | None:
        view = self.tabs.currentWidget()
        return view if isinstance(view, SheetView) else None

    def fit_current(self) -> None:
        view = self.current_view()
        if view is not None:
            view.fit_to_window()

    def _zoom_current(self, factor: float) -> None:
        view = self.current_view()
        if view is not None:
            view.zoom(factor)

    def show_sheet(self, sheet_index: int) -> None:
        for i, view in enumerate(self.views):
            if view.sheet_scene.sheet.index == sheet_index:
                self.tabs.setCurrentIndex(i)
                return

    # ------------------------------------------------------------------ selección
    def _view_for(self, sheet_index: int) -> SheetView | None:
        return next((v for v in self.views if v.sheet_scene.sheet.index == sheet_index), None)

    def _on_scene_selection(self, scene: SheetScene) -> None:
        # Al destruirse, la escena vacía su selección y emite selectionChanged.
        if self._syncing or not Shiboken.isValid(scene):
            return
        selected = scene.selectedItems()
        if not selected:
            return
        item = selected[0]
        if isinstance(item, PieceItem):
            self.piece_selected.emit(scene.sheet.index, item.placement_index)
        elif isinstance(item, CutLineItem):
            self.cut_selected.emit(scene.sheet.index, item.cut.order)

    def _select_item(self, view: SheetView, item: QGraphicsItem) -> None:
        self._syncing = True
        try:
            for scene in self.scenes:
                scene.clearSelection()
            self.tabs.setCurrentWidget(view)
            item.setSelected(True)
        finally:
            self._syncing = False
        view.ensureVisible(item)

    def select_piece(self, sheet_index: int, placement_index: int) -> bool:
        """Resalta una pieza (cambiando de pestaña si hace falta) sin emitir señales."""
        view = self._view_for(sheet_index)
        if view is None or not 0 <= placement_index < len(view.sheet_scene.piece_items):
            return False
        self._select_item(view, view.sheet_scene.piece_items[placement_index])
        return True

    def select_cut(self, sheet_index: int, cut_order: int) -> bool:
        """Resalta un corte; activa la capa de líneas de corte si estaba oculta."""
        view = self._view_for(sheet_index)
        if view is None or cut_order not in view.sheet_scene.cut_items:
            return False
        if not self.cuts_check.isChecked():
            self.cuts_check.setChecked(True)
        self._select_item(view, view.sheet_scene.cut_items[cut_order])
        return True

    def selected_piece(self) -> tuple[int, int] | None:
        for scene in self.scenes:
            for item in scene.selectedItems():
                if isinstance(item, PieceItem):
                    return scene.sheet.index, item.placement_index
        return None
