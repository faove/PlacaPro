"""Orquestador de la optimización: prueba estrategias × ordenamientos, búsqueda local
y se queda con la mejor solución válida según ``scoring.Score``.

Flujo de un intento: ordenar piezas → colocar en placas (secuencial o global) →
convertir a coordenadas reales → descomponer en guillotina (descarta lo que no se
puede cortar en modo escuadradora) → puntuar.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from models.parametros import CutMode, CuttingParameters, OptimizationLevel
from models.pieza import PieceInstance
from models.placa import PlateFormat
from models.resultado import (
    OptimizationResult,
    Placement,
    SheetLayout,
    SheetSource,
    UnplacedPiece,
)
from models.retazo import Offcut
from optimization.guillotine import Decomposition, decompose
from optimization.packing import Candidate, GuillotinePacker, MaxRectsPacker, Packer, PackerConfig
from optimization.scoring import Score
from optimization.space import BinSpec, fits_in_bin, lower_bound, piece_rotations
from utils.geometry import Rect
from utils.units import format_length


class OptimizationCancelled(Exception):
    """El usuario canceló la optimización antes de obtener una solución."""


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


# --------------------------------------------------------------------------- estrategias

ORDERINGS: dict[str, Callable[[PieceInstance], tuple]] = {
    "area": lambda p: (-p.area, -max(p.width, p.height), p.uid),
    "lado_mayor": lambda p: (-max(p.width, p.height), -min(p.width, p.height), p.uid),
    "perimetro": lambda p: (-(p.width + p.height), -p.area, p.uid),
    "ancho": lambda p: (-p.width, -p.height, p.uid),
    "alto": lambda p: (-p.height, -p.width, p.uid),
    "diferencia_lados": lambda p: (-abs(p.width - p.height), -p.area, p.uid),
}

SEQUENTIAL = "secuencial"
"""Llena una placa al máximo antes de abrir la siguiente."""
GLOBAL = "global"
"""Cada pieza va a la placa abierta donde mejor encaja."""
BEST_FIT = "mejor_ajuste"
"""En cada paso coloca la combinación pieza/hueco con mejor ajuste (el orden solo desempata).
Reconstruye bien los encajes exactos, pero es O(n²) por placa."""


@dataclass(frozen=True)
class Strategy:
    packer: PackerConfig
    mode: str = SEQUENTIAL

    @property
    def name(self) -> str:
        return f"{self.packer.name} ({self.mode})"


def _guillotine(sel: str, split: str, mode: str = SEQUENTIAL) -> Strategy:
    return Strategy(PackerConfig("guillotine", sel, split), mode)


def _maxrects(h: str, mode: str = SEQUENTIAL) -> Strategy:
    return Strategy(PackerConfig("maxrects", h), mode)


SHELF = Strategy(PackerConfig("shelf"))

PATIENCE_AT_LOWER_BOUND = 150
"""Iteraciones sin mejora tras alcanzar la cota inferior de placas."""


@dataclass(frozen=True)
class LevelPlan:
    orderings: tuple[str, ...]
    strategies: tuple[Strategy, ...]
    """Se prueban con cada ordenamiento."""
    best_fit: tuple[Strategy, ...]
    """Modo mejor ajuste: el orden casi no influye, se prueban una sola vez."""
    local_search_iterations: int
    patience: int
    time_budget_s: float


def level_plan(level: OptimizationLevel) -> LevelPlan:
    if level is OptimizationLevel.FAST:
        return LevelPlan(
            ("area", "lado_mayor", "alto"),
            (_guillotine("baf", "slas"), _guillotine("bssf", "slas"), SHELF),
            (_guillotine("baf", "slas", BEST_FIT),),
            0,
            0,
            2.0,
        )
    full = (
        *(
            _guillotine(sel, split)
            for sel in GuillotinePacker.SELECTIONS
            for split in ("slas", "llas", "minas", "maxas")
        ),
        _guillotine("baf", "slas", GLOBAL),
        _guillotine("bssf", "slas", GLOBAL),
        *(_maxrects(h) for h in MaxRectsPacker.HEURISTICS),
        _maxrects("bssf", GLOBAL),
        SHELF,
    )
    best_fit = (
        *(
            _guillotine(sel, split, BEST_FIT)
            for sel in ("baf", "bssf")
            for split in ("slas", "llas")
        ),
        _maxrects("baf", BEST_FIT),
        _maxrects("bssf", BEST_FIT),
    )
    if level is OptimizationLevel.BALANCED:
        return LevelPlan(tuple(ORDERINGS), full, best_fit, 60, 60, 8.0)
    return LevelPlan(tuple(ORDERINGS), full, best_fit, 4000, 800, 25.0)


# --------------------------------------------------------------------------- intento


@dataclass
class _OpenSheet:
    bin: BinSpec
    packer: Packer
    items: list[tuple[PieceInstance, Candidate]] = field(default_factory=list)


@dataclass
class Attempt:
    strategy: Strategy
    ordering: str
    order: list[PieceInstance]
    sheets: list[SheetLayout]
    unplaced: list[PieceInstance]
    decompositions: list[Decomposition | None]
    score: Score | None
    """``None`` si la solución no es válida (p. ej. no guillotinable en escuadradora)."""

    def sheet_uids(self, sheet_index: int) -> set[int]:
        return {p.piece.uid for p in self.sheets[sheet_index].placements}


@dataclass(frozen=True)
class OptimizationRequest:
    pieces: Sequence[PieceInstance]
    plate: PlateFormat
    params: CuttingParameters
    stock_plates: int = 0
    """Placas del inventario (se usan primero si ``params.use_stock_first``)."""
    offcuts: Sequence[Offcut] = ()
    """Retazos en stock (se usan primero si ``params.use_offcuts_first``)."""


_SOURCE_RANK = {SheetSource.OFFCUT: 0, SheetSource.STOCK: 1, SheetSource.NEW: 2}


class Optimizer:
    def __init__(
        self,
        request: OptimizationRequest,
        *,
        cancel: CancellationToken | None = None,
        on_progress: Callable[[float, Score | None], None] | None = None,
        time_budget_s: float | None = None,
    ) -> None:
        self.request = request
        self.params = request.params
        self.gap = self.params.cut_gap
        self.cancel = cancel or CancellationToken()
        self.on_progress = on_progress
        self.plan = level_plan(self.params.level)
        self.time_budget_s = time_budget_s if time_budget_s is not None else self.plan.time_budget_s
        self.rng = random.Random(self.params.seed)

        self.template = BinSpec.from_plate(request.plate, self.params)
        finite: list[BinSpec] = []
        if self.params.use_offcuts_first:
            finite += [
                BinSpec.from_offcut(o, self.params, request.plate.grain)
                for o in sorted(request.offcuts, key=lambda o: (o.area, o.id or 0))
            ]
        if self.params.use_stock_first:
            stock = BinSpec.from_plate(request.plate, self.params, SheetSource.STOCK)
            finite += [stock] * max(request.stock_plates, 0)
        self.finite_bins = finite
        self.rotations = {
            p.uid: piece_rotations(p, request.plate.grain, self.params) for p in request.pieces
        }
        self.attempts = 0

    # -- utilidades
    def _unplaceable_reason(self, piece: PieceInstance) -> str:
        m = self.template.margin
        uw = format_length(self.template.width - 2 * m)
        uh = format_length(self.template.height - 2 * m)
        rotations = self.rotations[piece.uid]
        detail = "" if len(rotations) > 1 else " sin girarla (veta/orientación)"
        return (
            f"{piece.label} ({piece.spec.dimensions_label} mm) no cabe{detail} en la superficie "
            f"útil de la placa ({uw} × {uh} mm)"
        )

    def _time_left(self, start: float) -> bool:
        return time.perf_counter() - start < self.time_budget_s

    # -- colocación
    def _pack(
        self, strategy: Strategy, order: Sequence[PieceInstance]
    ) -> tuple[list[_OpenSheet], list[PieceInstance]]:
        gap = self.gap
        unopened = list(self.finite_bins)
        sheets: list[_OpenSheet] = []
        unplaced: list[PieceInstance] = []

        def open_sheet(bin_spec: BinSpec) -> _OpenSheet:
            sheet = _OpenSheet(bin_spec, strategy.packer.create(*bin_spec.packing_size(gap)))
            sheets.append(sheet)
            return sheet

        if strategy.mode == BEST_FIT:
            remaining = list(order)
            while remaining:
                bin_spec = unopened.pop(0) if unopened else self.template
                sheet = open_sheet(bin_spec)
                while remaining:
                    best_k, best_c = -1, None
                    for k, piece in enumerate(remaining):
                        cand = sheet.packer.find(
                            piece.width + gap, piece.height + gap, self.rotations[piece.uid]
                        )
                        if cand is not None and (best_c is None or cand.key < best_c.key):
                            best_k, best_c = k, cand
                    if best_c is None:
                        break
                    sheet.packer.place(best_c)
                    sheet.items.append((remaining.pop(best_k), best_c))
                if not sheet.items:
                    sheets.pop()
                    if bin_spec is self.template:
                        unplaced.extend(remaining)
                        break
            return sheets, unplaced

        if strategy.mode == SEQUENTIAL:
            remaining = list(order)
            while remaining:
                bin_spec = unopened.pop(0) if unopened else self.template
                sheet = open_sheet(bin_spec)
                rest: list[PieceInstance] = []
                for piece in remaining:
                    cand = sheet.packer.find(
                        piece.width + gap, piece.height + gap, self.rotations[piece.uid]
                    )
                    if cand is None:
                        rest.append(piece)
                    else:
                        sheet.packer.place(cand)
                        sheet.items.append((piece, cand))
                if not sheet.items:
                    sheets.pop()
                    if bin_spec is self.template:
                        unplaced.extend(rest)
                        break
                remaining = rest
            return sheets, unplaced

        for piece in order:
            w, h, rots = piece.width + gap, piece.height + gap, self.rotations[piece.uid]
            best: tuple[_OpenSheet, Candidate] | None = None
            for sheet in sheets:
                cand = sheet.packer.find(w, h, rots)
                if cand is not None and (best is None or cand.key < best[1].key):
                    best = (sheet, cand)
            if best is None:
                bin_spec = next(
                    (b for b in unopened if fits_in_bin(piece, rots, b, gap)), self.template
                )
                if bin_spec is not self.template:
                    unopened.remove(bin_spec)
                sheet = open_sheet(bin_spec)
                cand = sheet.packer.find(w, h, rots)
                if cand is None:
                    sheets.pop()
                    unplaced.append(piece)
                    continue
                best = (sheet, cand)
            best[0].packer.place(best[1])
            best[0].items.append((piece, best[1]))
        return sheets, unplaced

    def _attempt(self, strategy: Strategy, ordering: str, order: list[PieceInstance]) -> Attempt:
        self.attempts += 1
        packed, unplaced = self._pack(strategy, order)
        packed.sort(
            key=lambda s: (
                _SOURCE_RANK[s.bin.source],
                -sum(p.area for p, _ in s.items),
            )
        )
        sheets: list[SheetLayout] = []
        decomps: list[Decomposition | None] = []
        valid = True
        for index, sheet in enumerate(packed):
            b, m, gap = sheet.bin, sheet.bin.margin, self.gap
            placements = tuple(
                Placement(piece, index, c.x + m, c.y + m, c.w - gap, c.h - gap, c.rotated)
                for piece, c in sheet.items
            )
            layout = SheetLayout(
                index=index,
                width=b.width,
                height=b.height,
                thickness=b.thickness,
                source=b.source,
                plate_format_id=b.plate_format_id,
                source_offcut_id=b.offcut_id,
                placements=placements,
                edge_margin=m,
            )
            decomp = decompose(
                [p.rect for p in placements], Rect(0, 0, b.width, b.height), self.params.kerf
            )
            if decomp is None and self.params.cut_mode is CutMode.PANEL_SAW:
                valid = False
            sheets.append(layout)
            decomps.append(decomp)

        score = None
        if valid:
            full = [s for s in sheets if s.source is not SheetSource.OFFCUT]
            score = Score(
                unplaced=len(unplaced),
                full_sheets=len(full),
                neg_offcut_sheets=len(full) - len(sheets),
                least_filled_area=min((s.used_area for s in full), default=0),
                neg_largest_leftover=-max(
                    (d.largest_leftover_area for d in decomps if d is not None), default=0
                ),
                cut_count=sum(d.cut_count for d in decomps if d is not None),
                cut_length=sum(d.total_cut_length for d in decomps if d is not None),
            )
        return Attempt(strategy, ordering, list(order), sheets, unplaced, decomps, score)

    # -- búsqueda local
    def _perturb(
        self, current: Attempt, strategies: Sequence[Strategy]
    ) -> tuple[Strategy, list[PieceInstance]]:
        rng = self.rng
        order = list(current.order)
        strategy = current.strategy
        n = len(order)
        op = rng.random()
        if n < 2 or op >= 0.85:
            strategy = rng.choice(strategies)
        elif op < 0.3:
            i, j = rng.sample(range(n), 2)
            order[i], order[j] = order[j], order[i]
        elif op < 0.5:
            order.insert(0, order.pop(rng.randrange(n)))
        elif op < 0.7:
            full = [s for s in current.sheets if s.source is not SheetSource.OFFCUT]
            if len(full) > 1:
                target = min(full, key=lambda s: s.used_area)
                uids = current.sheet_uids(target.index)
                moved = [p for p in order if p.uid in uids]
                rng.shuffle(moved)
                order = moved + [p for p in order if p.uid not in uids]
            else:
                i, j = sorted(rng.sample(range(n), 2))
                order[i : j + 1] = reversed(order[i : j + 1])
        else:
            i, j = sorted(rng.sample(range(n), 2))
            order[i : j + 1] = reversed(order[i : j + 1])
        return strategy, order

    # -- ejecución
    def run(self) -> OptimizationResult:
        start = time.perf_counter()
        pieces = list(self.request.pieces)
        placeable = [
            p for p in pieces if fits_in_bin(p, self.rotations[p.uid], self.template, self.gap)
        ]
        placeable_ids = {p.uid for p in placeable}
        fixed_unplaced = [
            UnplacedPiece(p, self._unplaceable_reason(p))
            for p in pieces
            if p.uid not in placeable_ids
        ]
        lb = lower_bound(placeable, self.template, self.gap)

        plan = self.plan
        total = (
            len(plan.orderings) * len(plan.strategies)
            + len(plan.best_fit)
            + plan.local_search_iterations
        )
        best: Attempt | None = None
        by_strategy: dict[Strategy, Attempt] = {}
        done = 0
        runs = [(o, plan.strategies) for o in plan.orderings] + [("area", plan.best_fit)]
        for ordering, strategies in runs:
            order = sorted(placeable, key=ORDERINGS[ordering])
            for strategy in strategies:
                if self.cancel.cancelled or (best is not None and not self._time_left(start)):
                    break
                attempt = self._attempt(strategy, ordering, order)
                done += 1
                if attempt.score is not None:
                    previous = by_strategy.get(strategy)
                    if previous is None or attempt.score < previous.score:  # type: ignore[operator]
                        by_strategy[strategy] = attempt
                    if best is None or attempt.score < best.score:  # type: ignore[operator]
                        best = attempt
                self._progress(done, total, best)

        improved_by_search = False
        if (
            best is not None
            and plan.local_search_iterations
            and len(placeable) > 1
            and any(s.mode != BEST_FIT for s in by_strategy)
        ):
            # El modo mejor ajuste apenas depende del orden: no vale la pena perturbarlo.
            top = sorted(
                (s for s in by_strategy if s.mode != BEST_FIT),
                key=lambda s: by_strategy[s].score,  # type: ignore[arg-type,return-value]
            )[:5]
            current = best
            if current.strategy.mode == BEST_FIT:
                current = by_strategy[top[0]]
            stale = 0
            # Si ya se alcanzó la cota inferior de placas (óptimo demostrado), solo quedan
            # mejoras secundarias: se busca con menos paciencia.
            at_lower_bound = PATIENCE_AT_LOWER_BOUND
            for _ in range(plan.local_search_iterations):
                patience = plan.patience
                if best.score.full_sheets <= lb and not self.finite_bins:  # type: ignore[union-attr]
                    patience = min(patience, at_lower_bound)
                if self.cancel.cancelled or not self._time_left(start) or stale >= patience:
                    break
                strategy, order = self._perturb(current, top)
                attempt = self._attempt(strategy, current.ordering, order)
                done += 1
                stale += 1
                if attempt.score is not None:
                    if attempt.score <= current.score:  # type: ignore[operator]
                        current = attempt
                    if attempt.score < best.score:  # type: ignore[operator]
                        best = attempt
                        improved_by_search = True
                        stale = 0
                self._progress(done, total, best)

        if best is None:
            if self.cancel.cancelled:
                raise OptimizationCancelled("Optimización cancelada")
            raise RuntimeError("Ninguna estrategia produjo una solución válida")

        unplaced = fixed_unplaced + [
            UnplacedPiece(p, "No se pudo ubicar en ninguna placa") for p in best.unplaced
        ]
        name = f"{best.strategy.name}, orden por {best.ordering}"
        if improved_by_search:
            name += " + búsqueda local"
        self.best_attempt = best
        return OptimizationResult(
            params=self.params,
            sheets=tuple(best.sheets),
            unplaced=tuple(unplaced),
            strategy=name,
            score=best.score.as_tuple(),  # type: ignore[union-attr]
            lower_bound=lb,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )

    def _progress(self, done: int, total: int, best: Attempt | None) -> None:
        if self.on_progress is not None:
            self.on_progress(min(done / total, 1.0) if total else 1.0, best.score if best else None)


def optimize(request: OptimizationRequest, **kwargs) -> OptimizationResult:
    """Atajo: ``Optimizer(request, **kwargs).run()``."""
    return Optimizer(request, **kwargs).run()
