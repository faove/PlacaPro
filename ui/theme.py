"""Paleta de categorías y hoja de estilos (QSS). Fuente única de colores de la UI.

Ver docs/05-interfaz-de-usuario.md §4 y §8.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from models.pieza import PieceCategory

CATEGORY_COLORS: dict[PieceCategory, str] = {
    PieceCategory.LATERAL: "#4A90D9",
    PieceCategory.TAPA: "#5CB85C",
    PieceCategory.BASE: "#5CB85C",
    PieceCategory.FONDO: "#9B7FD4",
    PieceCategory.PUERTA: "#F0C419",
    PieceCategory.DIVISOR: "#D9534F",
    PieceCategory.ESTANTE: "#2EC4B6",
    PieceCategory.CAJON: "#F39C12",
    PieceCategory.ZOCALO: "#A1887F",
    PieceCategory.OTRO: "#8FA9C1",
}
OFFCUT_COLOR = "#C8E6C9"
WASTE_COLOR = "#BDBDBD"
ERROR_COLOR = "#D9534F"
ERROR_BACKGROUND = "#FDECEA"
WARNING_COLOR = "#F39C12"
PRIMARY_COLOR = "#2B6CB0"


def category_color(category: PieceCategory) -> QColor:
    return QColor(CATEGORY_COLORS[category])


def text_color_for(background: QColor | str) -> QColor:
    """Negro o blanco según la luminancia relativa del fondo (WCAG)."""
    color = QColor(background)

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminance = (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )
    # Contraste con negro (L+0.05)/0.05 frente a blanco 1.05/(L+0.05): punto de corte ≈ 0.179.
    return QColor("#000000") if luminance > 0.179 else QColor("#FFFFFF")


STYLESHEET = f"""
QToolBox::tab {{
    font-weight: bold;
    border: 1px solid palette(mid);
    border-radius: 4px;
    padding: 4px 8px;
}}
QToolBox::tab:selected {{
    background: palette(highlight);
    color: palette(highlighted-text);
}}
QGroupBox {{
    border: 1px solid palette(mid);
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QListWidget, QTableView {{
    border-radius: 4px;
}}
QPushButton {{
    border-radius: 4px;
    padding: 4px 10px;
}}
QPushButton#optimizeButton {{
    background: {PRIMARY_COLOR};
    color: white;
    font-size: 15px;
    font-weight: bold;
    padding: 12px;
    border: none;
    border-radius: 6px;
}}
QPushButton#optimizeButton:hover {{
    background: #2C5282;
}}
QPushButton#optimizeButton:disabled {{
    background: palette(mid);
}}
QLabel#sectionTitle {{
    font-weight: bold;
    font-size: 13px;
}}
"""


def apply_theme(app: QApplication, *, dark: bool = False) -> None:
    """Estilo Fusion + QSS base. ``dark`` activa una paleta oscura básica."""
    app.setStyle("Fusion")
    if dark:
        palette = QPalette()
        for role, color in (
            (QPalette.ColorRole.Window, "#2B2B2B"),
            (QPalette.ColorRole.WindowText, "#E0E0E0"),
            (QPalette.ColorRole.Base, "#1E1E1E"),
            (QPalette.ColorRole.AlternateBase, "#2B2B2B"),
            (QPalette.ColorRole.Text, "#E0E0E0"),
            (QPalette.ColorRole.Button, "#3C3C3C"),
            (QPalette.ColorRole.ButtonText, "#E0E0E0"),
            (QPalette.ColorRole.Highlight, PRIMARY_COLOR),
            (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
            (QPalette.ColorRole.ToolTipBase, "#3C3C3C"),
            (QPalette.ColorRole.ToolTipText, "#E0E0E0"),
        ):
            palette.setColor(role, QColor(color))
        app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
