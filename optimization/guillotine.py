"""Descomposición guillotina de una distribución: ¿se puede cortar con escuadradora?

Dado un conjunto de piezas (coordenadas reales) dentro de una región, construye un
árbol de cortes rectos de borde a borde, cada uno de ancho ``kerf``:

* **trim**: separa una franja vacía (retazo o desperdicio) del lado de la región que
  no tiene piezas; se elige siempre la franja de mayor área.
* **split**: corta la región en tiras por todas las líneas libres en una orientación
  (una tira por grupo de piezas).
* **piece**: hoja que coincide exactamente con una pieza.
* **empty**: hoja sin piezas (sobrante).
* **block**: región con varias piezas sin ninguna línea libre (solo con
  ``allow_blocks``, para el modo CNC); sus hijos son las piezas.

Si alguna región con varias piezas no admite ninguna línea libre, la distribución
NO es guillotinable y ``decompose`` devuelve ``None`` (salvo con ``allow_blocks``).

Cualquier línea libre preserva la guillotinabilidad de ambos lados, así que la elección
voraz de cortes no hace fallar a una distribución que sí es guillotinable.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from models.plan_corte import CutOrientation
from utils.geometry import Rect

H = CutOrientation.HORIZONTAL
V = CutOrientation.VERTICAL


@dataclass(frozen=True)
class GNode:
    region: Rect
    kind: str
    """``"split"``, ``"trim"``, ``"piece"``, ``"empty"`` o ``"block"``."""
    orientation: CutOrientation | None = None
    positions: tuple[int, ...] = ()
    """Inicio de la franja de kerf de cada corte (X si vertical, Y si horizontal)."""
    children: tuple[GNode, ...] = ()
    piece_index: int | None = None

    @property
    def cut_length(self) -> int:
        if self.orientation is None:
            return 0
        return self.region.h if self.orientation is V else self.region.w

    def walk(self) -> Iterator[GNode]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True)
class Decomposition:
    root: GNode

    @property
    def cut_count(self) -> int:
        return sum(len(n.positions) for n in self.root.walk())

    @property
    def total_cut_length(self) -> int:
        return sum(len(n.positions) * n.cut_length for n in self.root.walk())

    @property
    def leftovers(self) -> list[Rect]:
        return [n.region for n in self.root.walk() if n.kind == "empty"]

    @property
    def largest_leftover_area(self) -> int:
        return max((r.area for r in self.leftovers), default=0)


def _bbox(rects: Sequence[Rect]) -> Rect:
    x0 = min(r.x for r in rects)
    y0 = min(r.y for r in rects)
    return Rect(x0, y0, max(r.right for r in rects) - x0, max(r.bottom for r in rects) - y0)


def _empty(region: Rect) -> tuple[GNode, ...]:
    return () if region.is_empty else (GNode(region, "empty"),)


def _best_trim(region: Rect, box: Rect, kerf: int) -> GNode:
    """Corta la franja vacía más grande entre la región y el contorno de las piezas.

    Devuelve un nodo trim cuyo hijo con piezas es un ``GNode`` provisional (kind
    ``"pending"``) que el llamador reemplaza al recursar.
    """
    options: list[tuple[int, int, GNode]] = []
    r = region
    if box.right < r.right:  # derecha
        off = Rect(box.right + kerf, r.y, max(r.right - box.right - kerf, 0), r.h)
        rest = Rect(r.x, r.y, box.right - r.x, r.h)
        node = GNode(r, "trim", V, (box.right,), (GNode(rest, "pending"), *_empty(off)))
        options.append((off.area, 0, node))
    if box.bottom < r.bottom:  # abajo
        off = Rect(r.x, box.bottom + kerf, r.w, max(r.bottom - box.bottom - kerf, 0))
        rest = Rect(r.x, r.y, r.w, box.bottom - r.y)
        node = GNode(r, "trim", H, (box.bottom,), (GNode(rest, "pending"), *_empty(off)))
        options.append((off.area, 1, node))
    if box.x > r.x:  # izquierda
        off = Rect(r.x, r.y, max(box.x - kerf - r.x, 0), r.h)
        rest = Rect(box.x, r.y, r.right - box.x, r.h)
        node = GNode(r, "trim", V, (box.x - kerf,), (*_empty(off), GNode(rest, "pending")))
        options.append((off.area, 2, node))
    if box.y > r.y:  # arriba
        off = Rect(r.x, r.y, r.w, max(box.y - kerf - r.y, 0))
        rest = Rect(r.x, box.y, r.w, r.bottom - box.y)
        node = GNode(r, "trim", H, (box.y - kerf,), (*_empty(off), GNode(rest, "pending")))
        options.append((off.area, 3, node))
    return max(options, key=lambda o: (o[0], -o[1]))[2]


def _free_lines(
    rects: Sequence[Rect], idx: list[int], orientation: CutOrientation, kerf: int
) -> tuple[list[int], list[list[int]]]:
    """Posiciones de corte libres y los grupos de piezas resultantes, en orden."""
    if orientation is V:
        order = sorted(idx, key=lambda i: (rects[i].x, rects[i].y))

        def start(i: int) -> int:
            return rects[i].x

        def end(i: int) -> int:
            return rects[i].right
    else:
        order = sorted(idx, key=lambda i: (rects[i].y, rects[i].x))

        def start(i: int) -> int:
            return rects[i].y

        def end(i: int) -> int:
            return rects[i].bottom

    positions: list[int] = []
    groups: list[list[int]] = [[]]
    reach = None
    for i in order:
        if reach is not None and reach + kerf <= start(i):
            positions.append(reach)
            groups.append([])
        groups[-1].append(i)
        reach = end(i) if reach is None else max(reach, end(i))
    return positions, groups


def _build(
    rects: Sequence[Rect], idx: list[int], region: Rect, kerf: int, blocks: bool = False
) -> GNode | None:
    box = _bbox([rects[i] for i in idx])
    if box != region:
        node = _best_trim(region, box, kerf)
        children = []
        for child in node.children:
            if child.kind == "pending":
                built = _build(rects, idx, child.region, kerf, blocks)
                if built is None:
                    return None
                children.append(built)
            else:
                children.append(child)
        return GNode(region, node.kind, node.orientation, node.positions, tuple(children))

    if len(idx) == 1:
        return GNode(region, "piece", piece_index=idx[0])

    v_pos, v_groups = _free_lines(rects, idx, V, kerf)
    h_pos, h_groups = _free_lines(rects, idx, H, kerf)
    if not v_pos and not h_pos:
        if not blocks:
            return None
        pieces = tuple(GNode(rects[i], "piece", piece_index=i) for i in sorted(idx))
        return GNode(region, "block", children=pieces)
    # Más tiras primero; a igualdad, cortes más largos (a lo largo del lado mayor).
    prefer_v = (len(v_pos), region.h >= region.w) >= (len(h_pos), region.w > region.h)
    orientation, positions, groups = (V, v_pos, v_groups) if prefer_v else (H, h_pos, h_groups)

    children: list[GNode] = []
    lo = region.x if orientation is V else region.y
    bounds = [*positions, region.right if orientation is V else region.bottom]
    for group, hi in zip(groups, bounds, strict=True):
        if orientation is V:
            sub = Rect(lo, region.y, hi - lo, region.h)
        else:
            sub = Rect(region.x, lo, region.w, hi - lo)
        built = _build(rects, group, sub, kerf, blocks)
        if built is None:
            return None
        children.append(built)
        lo = hi + kerf
    return GNode(region, "split", orientation, tuple(positions), tuple(children))


def decompose(
    rects: Sequence[Rect], region: Rect, kerf: int, *, allow_blocks: bool = False
) -> Decomposition | None:
    """Árbol de cortes guillotina o ``None`` si la distribución no es guillotinable.

    Con ``allow_blocks`` nunca devuelve ``None``: las zonas no guillotinables quedan
    como nodos ``"block"``.
    """
    if not rects:
        return Decomposition(GNode(region, "empty"))
    needed = 10 * len(rects) + 200
    if sys.getrecursionlimit() < needed:
        sys.setrecursionlimit(needed)
    root = _build(rects, list(range(len(rects))), region, kerf, allow_blocks)
    return Decomposition(root) if root is not None else None


def is_guillotine(rects: Sequence[Rect], region: Rect, kerf: int) -> bool:
    return decompose(rects, region, kerf) is not None
