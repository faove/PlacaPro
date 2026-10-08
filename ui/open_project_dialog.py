"""Diálogo «Abrir proyecto»: lista de proyectos guardados."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.repositories import ProjectSummary


class OpenProjectDialog(QDialog):
    def __init__(self, projects: list[ProjectSummary], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Abrir proyecto")
        self.resize(560, 360)
        self.table = QTableWidget(len(projects), 3)
        self.table.setHorizontalHeaderLabels(["Nombre", "Piezas", "Modificado"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row, summary in enumerate(projects):
            name = QTableWidgetItem(summary.name)
            name.setData(Qt.ItemDataRole.UserRole, summary.id)
            name.setToolTip(summary.description)
            modified = summary.updated_at.astimezone().strftime("%d/%m/%Y %H:%M")
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(str(summary.piece_count)))
            self.table.setItem(row, 2, QTableWidgetItem(modified))
        if projects:
            self.table.selectRow(0)
        self.table.doubleClicked.connect(lambda _index: self.accept())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(bool(projects))
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def selected_project_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
