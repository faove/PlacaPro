"""Hilos de trabajo: la optimización corre en el ``QThreadPool`` sin congelar la UI.

Solo se ejecuta ``OptimizationService.compute`` (puro, sin base de datos); la validación
previa y el guardado del resultado ocurren en el hilo principal. Ver ADR-006.
"""

from __future__ import annotations

import logging
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal

from optimization.optimizer import CancellationToken, OptimizationCancelled
from optimization.scoring import Score
from services.optimization_service import OptimizationService, PreparedOptimization

log = logging.getLogger(__name__)


class WorkerSignals(QObject):
    progress = Signal(float)
    """Fracción 0..1 del trabajo previsto."""
    finished = Signal(object)
    """``OptimizationResult``."""
    failed = Signal(str)
    """Mensaje de error (el traceback va al log)."""
    cancelled = Signal()


class OptimizationWorker(QRunnable):
    """Ejecuta una optimización preparada. Se cancela con :meth:`cancel`.

    Si se cancela, se emite ``cancelled`` y se descarta la mejor solución parcial.
    """

    def __init__(
        self, prepared: PreparedOptimization, *, time_budget_s: float | None = None
    ) -> None:
        super().__init__()
        self.prepared = prepared
        self.time_budget_s = time_budget_s
        self.token = CancellationToken()
        self.signals = WorkerSignals()

    def cancel(self) -> None:
        self.token.cancel()

    def _on_progress(self, fraction: float, _best: Score | None) -> None:
        self.signals.progress.emit(fraction)

    def run(self) -> None:
        try:
            result = OptimizationService.compute(
                self.prepared,
                cancel=self.token,
                on_progress=self._on_progress,
                time_budget_s=self.time_budget_s,
            )
        except OptimizationCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - se informa a la UI en lugar de perderse
            log.error("Fallo en la optimización\n%s", traceback.format_exc())
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            if self.token.cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.finished.emit(result)
