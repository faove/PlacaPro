"""Algoritmos de colocación en una sola placa (espacio de empaquetado, piezas infladas).

* ``GuillotinePacker``: divide el espacio libre con cortes de borde a borde.
* ``MaxRectsPacker``: rectángulos libres maximales (más denso; puede no ser guillotinable).
* ``ShelfPacker``: tiras horizontales (FFDH); baseline siempre guillotinable.

Todos exponen ``find(w, h, rotations) -> Candidate | None`` y ``place(candidate)``.
``w``/``h`` son las medidas YA infladas con el kerf; ``rotations`` las orientaciones
permitidas (``False`` = como se dibujó, ``True`` = girada 90°). La clave ``key`` de un
candidato es menor cuanto mejor, y es comparable entre placas del mismo tipo de packer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from utils.geometry import Rect, subtract


@dataclass(frozen=True)
class Candidate:
    x: int
    y: int
    w: int
    h: int
    rotated: bool
    key: tuple
    ref: int = -1
    """Dato interno del packer (índice de rectángulo libre o de tira)."""

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.w, self.h)


class Packer(ABC):
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.used: list[Rect] = []

    @abstractmethod
    def find(self, w: int, h: int, rotations: tuple[bool, ...]) -> Candidate | None: ...

    @abstractmethod
    def place(self, candidate: Candidate) -> Rect: ...

    @staticmethod
    def _sizes(w: int, h: int, rotations: tuple[bool, ...]) -> list[tuple[int, int, bool]]:
        return [((h, w, True) if r else (w, h, False)) for r in rotations]


def _fit_score(heuristic: str, free: Rect, pw: int, ph: int) -> tuple[int, int]:
    lw, lh = free.w - pw, free.h - ph
    short, long_ = (lw, lh) if lw <= lh else (lh, lw)
    if heuristic == "bssf":
        return (short, long_)
    if heuristic == "blsf":
        return (long_, short)
    if heuristic == "baf":
        return (free.area - pw * ph, short)
    raise ValueError(f"Heurística desconocida: {heuristic}")


# --------------------------------------------------------------------------- Guillotine


class GuillotinePacker(Packer):
    """Guillotine bin packing (J. Jylänki, 2010) con selección y regla de división configurables.

    Selección: ``baf`` (best area fit), ``bssf`` (best short side fit), ``blsf``.
    División: ``slas``/``llas`` (eje sobrante más corto/largo), ``minas``/``maxas``
    (minimizar/maximizar área), ``sas``/``las`` (eje corto/largo del rectángulo libre).
    """

    SELECTIONS = ("baf", "bssf", "blsf")
    SPLITS = ("slas", "llas", "minas", "maxas", "sas", "las")

    def __init__(
        self,
        width: int,
        height: int,
        selection: str = "baf",
        split: str = "slas",
        merge: bool = True,
    ) -> None:
        super().__init__(width, height)
        if selection not in self.SELECTIONS or split not in self.SPLITS:
            raise ValueError(f"Configuración inválida: {selection}/{split}")
        self.selection = selection
        self.split = split
        self.merge = merge
        self.free: list[Rect] = [Rect(0, 0, width, height)] if width > 0 and height > 0 else []

    def find(self, w: int, h: int, rotations: tuple[bool, ...]) -> Candidate | None:
        best: Candidate | None = None
        sizes = self._sizes(w, h, rotations)
        for i, free in enumerate(self.free):
            for pw, ph, rot in sizes:
                if pw <= free.w and ph <= free.h:
                    key = (*_fit_score(self.selection, free, pw, ph), free.y, free.x, rot)
                    if best is None or key < best.key:
                        best = Candidate(free.x, free.y, pw, ph, rot, key, i)
        return best

    def _split_horizontal(self, free: Rect, pw: int, ph: int) -> bool:
        lw, lh = free.w - pw, free.h - ph
        rule = self.split
        if rule == "slas":
            return lw <= lh
        if rule == "llas":
            return lw > lh
        if rule == "minas":
            return pw * lh > lw * ph
        if rule == "maxas":
            return pw * lh <= lw * ph
        if rule == "sas":
            return free.w <= free.h
        return free.w > free.h  # las

    def place(self, candidate: Candidate) -> Rect:
        free = self.free.pop(candidate.ref)
        pw, ph = candidate.w, candidate.h
        placed = Rect(free.x, free.y, pw, ph)
        lw, lh = free.w - pw, free.h - ph
        if self._split_horizontal(free, pw, ph):
            bottom = Rect(free.x, free.y + ph, free.w, lh)
            right = Rect(free.x + pw, free.y, lw, ph)
        else:
            right = Rect(free.x + pw, free.y, lw, free.h)
            bottom = Rect(free.x, free.y + ph, pw, lh)
        for part in (bottom, right):
            if not part.is_empty:
                self.free.append(part)
        if self.merge:
            self._merge_free()
        self.used.append(placed)
        return placed

    def _merge_free(self) -> None:
        free = self.free
        changed = True
        while changed:
            changed = False
            for i in range(len(free)):
                a = free[i]
                for j in range(i + 1, len(free)):
                    b = free[j]
                    merged = None
                    if a.x == b.x and a.w == b.w:
                        if a.bottom == b.y:
                            merged = Rect(a.x, a.y, a.w, a.h + b.h)
                        elif b.bottom == a.y:
                            merged = Rect(a.x, b.y, a.w, a.h + b.h)
                    elif a.y == b.y and a.h == b.h:
                        if a.right == b.x:
                            merged = Rect(a.x, a.y, a.w + b.w, a.h)
                        elif b.right == a.x:
                            merged = Rect(b.x, a.y, a.w + b.w, a.h)
                    if merged is not None:
                        free[i] = merged
                        del free[j]
                        changed = True
                        break
                if changed:
                    break


# --------------------------------------------------------------------------- MaxRects


class MaxRectsPacker(Packer):
    """MaxRects (J. Jylänki, 2010). Heurísticas: ``bssf``, ``blsf``, ``baf``, ``bl``
    (bottom-left) y ``cp`` (contact point)."""

    HEURISTICS = ("bssf", "blsf", "baf", "bl", "cp")

    def __init__(self, width: int, height: int, heuristic: str = "bssf") -> None:
        super().__init__(width, height)
        if heuristic not in self.HEURISTICS:
            raise ValueError(f"Heurística desconocida: {heuristic}")
        self.heuristic = heuristic
        self.free: list[Rect] = [Rect(0, 0, width, height)] if width > 0 and height > 0 else []

    def _contact(self, x: int, y: int, w: int, h: int) -> int:
        score = 0
        if x == 0 or x + w == self.width:
            score += h
        if y == 0 or y + h == self.height:
            score += w
        for u in self.used:
            if u.x == x + w or u.right == x:
                score += max(0, min(u.bottom, y + h) - max(u.y, y))
            if u.y == y + h or u.bottom == y:
                score += max(0, min(u.right, x + w) - max(u.x, x))
        return score

    def find(self, w: int, h: int, rotations: tuple[bool, ...]) -> Candidate | None:
        best: Candidate | None = None
        sizes = self._sizes(w, h, rotations)
        for free in self.free:
            for pw, ph, rot in sizes:
                if pw > free.w or ph > free.h:
                    continue
                if self.heuristic == "bl":
                    primary: tuple[int, ...] = (free.y + ph, free.x)
                elif self.heuristic == "cp":
                    primary = (-self._contact(free.x, free.y, pw, ph),)
                else:
                    primary = _fit_score(self.heuristic, free, pw, ph)
                key = (*primary, free.y, free.x, rot)
                if best is None or key < best.key:
                    best = Candidate(free.x, free.y, pw, ph, rot, key)
        return best

    def place(self, candidate: Candidate) -> Rect:
        placed = candidate.rect
        kept: list[Rect] = []
        new_parts: list[Rect] = []
        for free in self.free:
            if free.intersects(placed):
                new_parts.extend(p for p in subtract(free, placed) if not p.is_empty)
            else:
                kept.append(free)
        # Poda incremental: los libres previos ya eran maximales entre sí.
        unique_new: list[Rect] = []
        for i, part in enumerate(new_parts):
            if any(k.contains(part) for k in kept):
                continue
            if any(
                j != i and other.contains(part) and (other != part or j < i)
                for j, other in enumerate(new_parts)
            ):
                continue
            unique_new.append(part)
        kept = [k for k in kept if not any(n.contains(k) for n in unique_new)]
        self.free = kept + unique_new
        self.used.append(placed)
        return placed


# --------------------------------------------------------------------------- Shelf


@dataclass
class _Shelf:
    y: int
    h: int
    used_w: int = 0


class ShelfPacker(Packer):
    """Tiras horizontales First Fit: cada tira tiene la altura de su primera pieza."""

    def __init__(self, width: int, height: int) -> None:
        super().__init__(width, height)
        self.shelves: list[_Shelf] = []
        self.next_y = 0

    def find(self, w: int, h: int, rotations: tuple[bool, ...]) -> Candidate | None:
        sizes = self._sizes(w, h, rotations)
        best: Candidate | None = None
        for si, shelf in enumerate(self.shelves):
            for pw, ph, rot in sizes:
                if ph <= shelf.h and shelf.used_w + pw <= self.width:
                    key = (0, si, shelf.h - ph, rot)
                    if best is None or key < best.key:
                        best = Candidate(shelf.used_w, shelf.y, pw, ph, rot, key, si)
            if best is not None:
                return best
        for pw, ph, rot in sizes:
            if self.next_y + ph <= self.height and pw <= self.width:
                key = (1, ph, rot)
                if best is None or key < best.key:
                    best = Candidate(0, self.next_y, pw, ph, rot, key, -1)
        return best

    def place(self, candidate: Candidate) -> Rect:
        if candidate.ref < 0:
            self.shelves.append(_Shelf(self.next_y, candidate.h, candidate.w))
            self.next_y += candidate.h
        else:
            self.shelves[candidate.ref].used_w += candidate.w
        placed = candidate.rect
        self.used.append(placed)
        return placed


# --------------------------------------------------------------------------- registro


@dataclass(frozen=True)
class PackerConfig:
    """Configuración de un algoritmo de colocación."""

    kind: str
    heuristic: str = ""
    split: str = ""
    options: tuple[tuple[str, object], ...] = field(default=())

    @property
    def name(self) -> str:
        return "-".join(p for p in (self.kind, self.heuristic, self.split) if p)

    def create(self, width: int, height: int) -> Packer:
        return STRATEGIES[self.kind](width, height, self)


STRATEGIES: dict[str, Callable[[int, int, PackerConfig], Packer]] = {
    "guillotine": lambda w, h, c: GuillotinePacker(
        w, h, c.heuristic or "baf", c.split or "slas", **dict(c.options)
    ),
    "maxrects": lambda w, h, c: MaxRectsPacker(w, h, c.heuristic or "bssf"),
    "shelf": lambda w, h, c: ShelfPacker(w, h),
}
"""Registro de algoritmos: añadir uno nuevo = añadir una entrada."""
