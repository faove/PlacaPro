"""Panel derecho: tarjetas KPI, tabla por placa y aviso de piezas no ubicadas.

Todas las cifras salen de las métricas de ``OptimizationResult`` / ``SheetLayout``
(áreas enteras en dmm², mostradas en m²; longitudes en la unidad visible).
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.resultado import OptimizationResult, SheetLayout
from ui.units_display import UnitsDisplay
from utils.units import format_area_m2

EMPTY_MESSAGE = "Pulse <b>OPTIMIZAR CORTES</b> para calcular."
SHEET_HEADERS = ["Placa", "Origen", "Medidas", "Piezas", "Aprov.", "Usada", "Desperd.", "Retazos"]


def percent(fraction: float) -> str:
    return f"{fraction * 100:.1f} %".replace(".", ",")


def result_kpis(result: OptimizationResult) -> dict[str, str]:
    """Tarjetas principales (título → valor), en orden de presentación."""
    return {
        "Placas necesarias": str(result.sheets_count),
        "Área total": format_area_m2(result.total_area),
        "Área utilizada": format_area_m2(result.used_area),
        "Desperdicio": format_area_m2(result.waste_area),
        "Aprovechamiento": percent(result.utilization),
        "Nº de piezas": str(result.pieces_count),
    }


def result_details(result: OptimizationResult) -> dict[str, str]:
    """Datos secundarios del cálculo."""
    return {
        "Retazos reutilizables": format_area_m2(result.reusable_offcut_area),
        "Cota inferior": f"{result.lower_bound} placa{'' if result.lower_bound == 1 else 's'}",
        "Tiempo": f"{result.duration_ms} ms",
        "Estrategia": result.strategy or "—",
    }


def sheet_row(sheet: SheetLayout, units: UnitsDisplay) -> list[str]:
    return [
        str(sheet.index + 1),
        sheet.source.label,
        f"{units.format(sheet.width)} × {units.format(sheet.height)}",
        str(len(sheet.placements)),
        percent(sheet.utilization),
        format_area_m2(sheet.used_area),
        format_area_m2(sheet.waste_area),
        format_area_m2(sheet.reusable_offcut_area),
    ]


class KpiCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.title_label = QLabel(title)
        self.title_label.setObjectName("kpiTitle")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("kpiValue")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(0)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class ResultWidget(QScrollArea):
    """Resumen del resultado. Clic en una fila de la tabla → ``sheet_activated(índice)``."""

    sheet_activated = Signal(int)
    confirm_requested = Signal()

    def __init__(self, units: UnitsDisplay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.units = units
        self.result: OptimizationResult | None = None
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        title = QLabel("RESULTADO")
        title.setObjectName("sectionTitle")
        self.stale_banner = QLabel(
            "⚠ <b>Resultado desactualizado</b>: los datos cambiaron desde el cálculo."
        )
        self.stale_banner.setObjectName("staleBanner")
        self.stale_banner.setWordWrap(True)
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setTextFormat(Qt.TextFormat.RichText)
        self.unplaced_banner = QLabel()
        self.unplaced_banner.setObjectName("unplacedBanner")
        self.unplaced_banner.setWordWrap(True)
        self.unplaced_banner.setTextFormat(Qt.TextFormat.RichText)

        self.cards: dict[str, KpiCard] = {}
        self.kpi_box = QWidget()
        grid = QGridLayout(self.kpi_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        for i, name in enumerate(
            [
                "Placas necesarias",
                "Área total",
                "Área utilizada",
                "Desperdicio",
                "Aprovechamiento",
                "Nº de piezas",
            ]
        ):
            card = KpiCard(name)
            self.cards[name] = card
            grid.addWidget(card, i // 2, i % 2)

        self.details_label = QLabel()
        self.details_label.setTextFormat(Qt.TextFormat.RichText)
        self.details_label.setWordWrap(True)

        self.sheets_title = QLabel("PLACAS")
        self.sheets_title.setObjectName("sectionTitle")
        self.sheet_table = QTableWidget(0, len(SHEET_HEADERS))
        self.sheet_table.setHorizontalHeaderLabels(SHEET_HEADERS)
        self.sheet_table.verticalHeader().hide()
        self.sheet_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sheet_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sheet_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sheet_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.sheet_table.setMinimumHeight(120)
        self.sheet_table.cellClicked.connect(self._on_sheet_clicked)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(title)
        layout.addWidget(self.stale_banner)
        layout.addWidget(self.message_label)
        layout.addWidget(self.unplaced_banner)
        layout.addWidget(self.kpi_box)
        layout.addWidget(self.details_label)
        layout.addWidget(self.sheets_title)
        layout.addWidget(self.sheet_table, 1)
        self.confirm_button = QPushButton("Confirmar y descontar stock")
        self.confirm_button.setToolTip(
            "Descuenta del inventario las placas usadas y marca como consumidos los retazos "
            "del stock que usa este plan"
        )
        self.confirm_button.clicked.connect(self.confirm_requested)
        self._confirm_state: tuple[bool, str] = (False, "")
        self.confirm_label = QLabel()
        self.confirm_label.setWordWrap(True)
        layout.addWidget(self.confirm_button)
        layout.addWidget(self.confirm_label)
        self.setWidget(body)

        units.unit_changed.connect(lambda _unit: self.set_result(self.result, keep_stale=True))
        self.set_result(None)

    # ------------------------------------------------------------------ contenido
    def set_result(self, result: OptimizationResult | None, *, keep_stale: bool = False) -> None:
        self.result = result
        if not keep_stale:
            self.stale_banner.hide()
        has = result is not None
        for widget in (self.kpi_box, self.details_label, self.sheets_title, self.sheet_table):
            widget.setVisible(has)
        self.message_label.setVisible(not has)
        self.message_label.setText(EMPTY_MESSAGE)
        self.unplaced_banner.hide()
        self.sheet_table.setRowCount(0)
        self.set_confirm_state(*self._confirm_state)
        if result is None:
            return

        for name, value in result_kpis(result).items():
            self.cards[name].set_value(value)
        self.details_label.setText(
            "<table cellspacing='2'>"
            + "".join(
                f"<tr><td>{k}:</td><td><b>{escape(v)}</b></td></tr>"
                for k, v in result_details(result).items()
            )
            + "</table>"
        )
        self.sheet_table.setRowCount(len(result.sheets))
        for r, sheet in enumerate(result.sheets):
            for c, text in enumerate(sheet_row(sheet, self.units)):
                item = QTableWidgetItem(text)
                if c not in (1, 2):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.sheet_table.setItem(r, c, item)
        self.sheet_table.setHorizontalHeaderItem(
            2, QTableWidgetItem(f"Medidas ({self.units.symbol})")
        )

        if result.unplaced:
            items = "".join(
                f"<li><b>{escape(u.piece.label)}</b>: {escape(u.reason)}</li>"
                for u in result.unplaced
            )
            self.unplaced_banner.setText(
                f"⚠ <b>{len(result.unplaced)} pieza{'s' if len(result.unplaced) != 1 else ''} "
                f"sin ubicar</b><ul style='margin:0'>{items}</ul>"
            )
            self.unplaced_banner.show()

    def set_message(self, html: str) -> None:
        """Muestra un mensaje en lugar del resultado (errores, cancelación…)."""
        self.set_result(None)
        self.message_label.setText(html)

    def set_confirm_state(self, enabled: bool, text: str) -> None:
        """Habilita «Confirmar» y muestra el estado de confirmación del plan."""
        self._confirm_state = (enabled, text)
        has = self.result is not None
        self.confirm_button.setVisible(has)
        self.confirm_button.setEnabled(has and enabled)
        self.confirm_label.setVisible(has and bool(text))
        self.confirm_label.setText(text)

    def set_stale(self, stale: bool) -> None:
        self.stale_banner.setVisible(stale and self.result is not None)

    def message_text(self) -> str:
        return self.message_label.text()

    def kpi_values(self) -> dict[str, str]:
        return {name: card.value_label.text() for name, card in self.cards.items()}

    def _on_sheet_clicked(self, row: int, _column: int) -> None:
        if self.result is not None and 0 <= row < len(self.result.sheets):
            self.sheet_activated.emit(self.result.sheets[row].index)
