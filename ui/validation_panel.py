"""Panel de mensajes de validación: lista clicable de ``ValidationIssue``."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from models.validation import Severity, ValidationIssue
from ui.theme import ERROR_COLOR, WARNING_COLOR

ICONS = {Severity.ERROR: "✖", Severity.WARNING: "⚠"}


class ValidationPanel(QWidget):
    """Muestra errores primero y luego avisos. Clic → ``issue_activated(ValidationIssue)``."""

    issue_activated = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = QLabel()
        self.title.setObjectName("sectionTitle")
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemActivated.connect(self._on_item)
        self.list.itemClicked.connect(self._on_item)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title)
        layout.addWidget(self.list, 1)
        self.set_issues([])

    def set_issues(self, issues: list[ValidationIssue]) -> None:
        self.issues = sorted(issues, key=lambda i: i.severity is not Severity.ERROR)
        self.list.clear()
        for issue in self.issues:
            entry = QListWidgetItem(f"{ICONS[issue.severity]}  {issue.message}")
            entry.setData(Qt.ItemDataRole.UserRole, issue)
            color = ERROR_COLOR if issue.severity is Severity.ERROR else WARNING_COLOR
            entry.setForeground(QColor(color))
            self.list.addItem(entry)
        errors = sum(1 for i in issues if i.severity is Severity.ERROR)
        warnings = len(issues) - errors
        if not issues:
            self.title.setText("Validación: sin problemas")
        else:
            self.title.setText(f"Validación: {errors} errores · {warnings} avisos")

    def _on_item(self, entry: QListWidgetItem) -> None:
        self.issue_activated.emit(entry.data(Qt.ItemDataRole.UserRole))
