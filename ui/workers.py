"""Hilos de trabajo: la optimización corre en el ``QThreadPool`` sin congelar la UI.

Solo se ejecuta ``OptimizationService.compute`` (puro, sin base de datos); la validación
previa y el guardado del resultado ocurren en el hilo principal. Ver ADR-006.
"""

from __future__ import annotations

import logging
import time
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal

from optimization.optimizer import CancellationToken, OptimizationCancelled
from optimization.scoring import Score
from services.optimization_service import OptimizationService, PreparedOptimization

log = logging.getLogger(__name__)

PROGRESS_INTERVAL_S = 0.05
"""Mínimo entre dos avisos de progreso (el optimizador informa en cada intento)."""

GIL_SWITCH_INTERVAL_S = 0.0005
"""Intervalo de cambio del GIL mientras hay una optimización en segundo plano.

Con el valor por defecto de Python (5 ms), cada llamada de Qt a código Python (pintar
la tabla de piezas, ``data()`` de los modelos…) espera hasta 5 ms a que el hilo del
optimizador suelte el GIL; con 200 piezas la ventana quedaba congelada ~2 s. Con 0,5 ms
la interfaz responde en < 50 ms y el optimizador no se vuelve más lento de forma medible.
Ver docs/benchmarks.md.
"""


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
        self._last_progress = float("-inf")

    def cancel(self) -> None:
        self.token.cancel()

    def _on_progress(self, fraction: float, _best: Score | None) -> None:
        now = time.monotonic()
        if fraction >= 1 or now - self._last_progress >= PROGRESS_INTERVAL_S:
            self._last_progress = now
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
