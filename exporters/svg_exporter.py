"""SVG: un archivo por placa con el diagrama (líneas de corte y cotas).

Exportador mínimo: muestra que un formato nuevo es un archivo + ``register(...)``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgGenerator

from exporters.base import ExportContext, register

SVG_WIDTH_PX = 1000


def svg_paths(path: Path, sheet_count: int) -> list[Path]:
    stem = path.with_suffix("")
    return [stem.with_name(f"{stem.name}_placa{i + 1}.svg") for i in range(sheet_count)]


class SvgExporter:
    id = "svg"
    name = "SVG (diagramas de las placas)…"
    file_filter = "SVG (*.svg)"
    suffix = ".svg"
    menu_order = 30

    def export(self, context: ExportContext, path: Path) -> list[Path]:
        from ui.cutting_diagram_widget import SheetScene  # mismo diagrama que la UI
        from ui.units_display import UnitsDisplay

        units = UnitsDisplay(context.unit)
        paths = svg_paths(Path(path), len(context.result.sheets))
        for sheet, out in zip(context.result.sheets, paths, strict=True):
            scene = SheetScene(sheet, units)
            scene.set_cuts_visible(True)
            scene.set_dimensions_visible(True)
            source = scene.sceneRect()
            height = round(SVG_WIDTH_PX * source.height() / source.width())
            generator = QSvgGenerator()
            generator.setFileName(str(out))
            generator.setSize(QSize(SVG_WIDTH_PX, height))
            generator.setViewBox(QRectF(0, 0, SVG_WIDTH_PX, height))
            generator.setTitle(f"{context.project.name} — placa {sheet.index + 1}")
            painter = QPainter(generator)
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                scene.render(
                    painter,
                    QRectF(0, 0, SVG_WIDTH_PX, height),
                    source,
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
            finally:
                painter.end()
            scene.deleteLater()
        units.deleteLater()
        return paths


register(SvgExporter())
