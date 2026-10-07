"""Plan de corte físico: del layout matemático a la secuencia de cortes del taller.

1. Árbol de cortes (``CutTree``) por descomposición guillotina de la placa
   (``guillotine.py``), con los sobrantes ya fusionados (``offcuts.py``). Los cortes
   paralelos de una misma región se agrupan en una **pasada**; cada cambio de
   orientación es un nivel más. El refilado de los cuatro bordes es el nivel 0.
2. Secuencia (docs/04-plan-de-corte-fisico.md §4.2): refilado → nivel 1 → nivel 2 → …
   Dentro de una región, de un extremo al otro; entre regiones del mismo nivel, primero
   las que tienen más piezas.
3. Cada corte lleva su posición absoluta, longitud, kerf efectivo, la **medida de tope**
   (distancia desde el borde de la región que se corta, es decir, el ancho de la franja
   que separa) y lo que libera.

El árbol es una partición exacta de la placa: piezas + kerf + sobrantes = área.
En modo CNC, si la distribución no es guillotinable, no hay secuencia de escuadradora:
se dan los contornos de las piezas y los sobrantes de la parte que sí se puede cortar.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, replace
from enum import Enum

from models.parametros import CutMode, CuttingParameters
from models.plan_corte import Cut, CutOrientation, CutPlan, PieceContour
from models.resultado import OptimizationResult, SheetLayout
from models.retazo import Offcut, OffcutStatus
from optimization.guillotine import GNode, decompose
from optimization.offcuts import classify, merge_offcuts
from utils.geometry import Rect
from utils.units import format_length

H = CutOrientation.HORIZONTAL
V = CutOrientation.VERTICAL


class NodeKind(Enum):
    CUT = "cut"
    """Región cortada por uno o más cortes paralelos (una pasada)."""
    PIECE = "piece"
    OFFCUT = "offcut"
    """Sobrante: retazo reutilizable o desperdicio."""
    EDGE = "edge"
    """Franja de refilado."""
    BLOCK = "block"
    """Zona no guillotinable (solo CNC): sus hijos son las piezas."""


@dataclass(frozen=True)
class CutNode:
    region: Rect
    kind: NodeKind
    level: int = 0
    orientation: CutOrientation | None = None
    positions: tuple[int, ...] = ()
    """Inicio de la franja de kerf de cada corte, en orden creciente."""
    children: tuple[CutNode, ...] = ()
    """En un ``CUT``: las franjas no vacías entre cortes, en orden de coordenada."""
    ref: int | None = None
    """Índice de la colocación (``PIECE``) o del sobrante (``OFFCUT``)."""
    label: str = ""

    def walk(self) -> Iterator[CutNode]:
        yield self
        for child in self.children:
            yield from child.walk()

    @property
    def piece_count(self) -> int:
        return sum(1 for n in self.walk() if n.kind is NodeKind.PIECE)


@dataclass(frozen=True)
class CutTree:
    root: CutNode

    def leaves(self, kind: NodeKind) -> list[CutNode]:
        return [n for n in self.root.walk() if n.kind is kind]


@dataclass(frozen=True)
class SheetPlan:
    tree: CutTree
    cut_plan: CutPlan
    offcuts: tuple[Offcut, ...]


# --------------------------------------------------------------------------- árbol


def _span(rect: Rect, orientation: CutOrientation) -> tuple[int, int]:
    """Extensión de ``rect`` en el eje que cortan los cortes de esa orientación."""
    return (rect.x, rect.right) if orientation is V else (rect.y, rect.bottom)


def _flatten(g: GNode, level: int, n_pieces: int) -> CutNode:
    """GNode → CutNode, uniendo en una pasada los cortes paralelos anidados.

    Un hijo cortado en la misma orientación que su padre tiene la misma extensión a lo
    largo del corte, así que sus cortes son de la misma pasada (mismo nivel).
    """
    if g.kind == "piece":
        idx = g.piece_index
        assert idx is not None
        if idx < n_pieces:
            return CutNode(g.region, NodeKind.PIECE, ref=idx)
        return CutNode(g.region, NodeKind.OFFCUT, ref=idx - n_pieces)
    if g.kind == "empty":
        return CutNode(g.region, NodeKind.OFFCUT)
    if g.kind == "block":
        children = tuple(_flatten(c, level + 1, n_pieces) for c in g.children)
        return CutNode(g.region, NodeKind.BLOCK, level, children=children)

    o = g.orientation
    assert o is not None
    positions: list[int] = []
    slices: list[GNode] = []

    def collect(n: GNode) -> None:
        positions.extend(n.positions)
        for c in n.children:
            if c.kind in ("split", "trim") and c.orientation is o:
                collect(c)
            else:
                slices.append(c)

    collect(g)
    slices.sort(key=lambda c: _span(c.region, o)[0])
    children = tuple(_flatten(c, level + 1, n_pieces) for c in slices)
    return CutNode(g.region, NodeKind.CUT, level, o, tuple(sorted(positions)), children)


def _letters(i: int) -> str:
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(ord("A") + r) + out
    return out


def _execution_order(children: tuple[CutNode, ...]) -> list[CutNode]:
    """Subregiones a cortar, primero las que tienen más piezas."""
    subs = [c for c in children if c.kind is NodeKind.CUT]
    return sorted(subs, key=lambda c: (-c.piece_count, c.region.y, c.region.x))


def _name(node: CutNode, label: str) -> CutNode:
    """Nombra las subregiones por posición: Tira A, B… y dentro de ellas A.1, A.2…"""
    children: list[CutNode] = []
    i = 0
    for c in node.children:
        if c.kind is NodeKind.CUT:
            sub = f"Tira {_letters(i)}" if label == "Placa" else f"{label}.{i + 1}"
            c = _name(c, sub)
            i += 1
        children.append(c)
    return replace(node, label=label, children=tuple(children))


def _edge(rect: Rect) -> tuple[CutNode, ...]:
    return () if rect.is_empty else (CutNode(rect, NodeKind.EDGE),)


def _with_edges(inner: CutNode, width: int, height: int, m: int, k: int) -> CutNode:
    """Refilado: izquierda y derecha (cortes verticales), luego arriba y abajo."""
    strip = max(m - k, 0)
    middle = Rect(m, 0, width - 2 * m, height)
    h_node = CutNode(
        middle,
        NodeKind.CUT,
        0,
        H,
        (m - k, height - m),
        (
            *_edge(Rect(m, 0, middle.w, strip)),
            inner,
            *_edge(Rect(m, height - m + k, middle.w, strip)),
        ),
        label="Placa",
    )
    return CutNode(
        Rect(0, 0, width, height),
        NodeKind.CUT,
        0,
        V,
        (m - k, width - m),
        (*_edge(Rect(0, 0, strip, height)), h_node, *_edge(Rect(width - m + k, 0, strip, height))),
        label="Placa",
    )


# --------------------------------------------------------------------------- planificador


class CuttingPlanner:
    def __init__(self, params: CuttingParameters, material_id: int | None = None) -> None:
        self.params = params
        self.material_id = material_id

    def build(self, sheet: SheetLayout) -> SheetPlan:
        k, m = self.params.kerf, sheet.edge_margin
        pieces = [p.rect for p in sheet.placements]
        inner = Rect(m, m, sheet.width - 2 * m, sheet.height - 2 * m)
        decomp = decompose(pieces, inner, k)
        if decomp is None:
            if self.params.cut_mode is not CutMode.CNC:
                raise ValueError(f"La placa {sheet.index + 1} no se puede cortar en guillotina")
            return self._build_cnc(sheet, pieces, inner)

        leftovers = merge_offcuts(pieces, decomp.leftovers, inner, k)
        final = decompose([*pieces, *leftovers], inner, k)
        assert final is not None
        root = _flatten(final.root, 1, len(pieces))
        root = _name(root, "Placa")
        if m > 0:
            root = _with_edges(root, sheet.width, sheet.height, m, k)
        tree = CutTree(root)
        offcuts = self._offcuts(sheet, tree)
        cuts = self._sequence(tree, sheet, offcuts)
        return SheetPlan(tree, CutPlan(sheet.index, tuple(cuts), CutMode.PANEL_SAW), offcuts)

    def plan(self, sheet: SheetLayout) -> CutPlan:
        return self.build(sheet).cut_plan

    def plan_sheet(self, sheet: SheetLayout) -> SheetLayout:
        """La placa con su plan de corte y sus retazos."""
        built = self.build(sheet)
        return replace(sheet, cut_plan=built.cut_plan, offcuts=built.offcuts)

    def _build_cnc(self, sheet: SheetLayout, pieces: list[Rect], inner: Rect) -> SheetPlan:
        decomp = decompose(pieces, inner, self.params.kerf, allow_blocks=True)
        assert decomp is not None
        tree = CutTree(_flatten(decomp.root, 1, len(pieces)))
        contours = tuple(
            PieceContour(p.piece.label, p.x, p.y, p.width, p.height) for p in sheet.placements
        )
        plan = CutPlan(sheet.index, (), CutMode.CNC, contours)
        return SheetPlan(tree, plan, self._offcuts(sheet, tree))

    def _offcuts(self, sheet: SheetLayout, tree: CutTree) -> tuple[Offcut, ...]:
        def make(rect: Rect, status: OffcutStatus, label: str = "", notes: str = "") -> Offcut:
            return Offcut(
                rect.w,
                rect.h,
                sheet.thickness,
                status,
                plate_format_id=sheet.plate_format_id,
                material_id=self.material_id,
                x=rect.x,
                y=rect.y,
                sheet_index=sheet.index,
                label=label,
                notes=notes,
            )

        rects = [n.region for n in tree.leaves(NodeKind.OFFCUT)]
        reusable = sorted(
            (r for r in rects if classify(r, self.params) is OffcutStatus.REUSABLE),
            key=lambda r: (-r.area, r.y, r.x),
        )
        waste = sorted(
            (r for r in rects if classify(r, self.params) is OffcutStatus.WASTE),
            key=lambda r: (r.y, r.x),
        )
        edges = [n.region for n in tree.leaves(NodeKind.EDGE)]
        return (
            *(
                make(r, OffcutStatus.REUSABLE, f"R{sheet.index + 1}.{i + 1}")
                for i, r in enumerate(reusable)
            ),
            *(make(r, OffcutStatus.WASTE) for r in waste),
            *(make(r, OffcutStatus.WASTE, notes="Refilado") for r in edges),
        )

    def _sequence(
        self, tree: CutTree, sheet: SheetLayout, offcuts: tuple[Offcut, ...]
    ) -> list[Cut]:
        k = self.params.kerf
        by_rect = {Rect(o.x, o.y, o.width, o.height): o for o in offcuts}  # type: ignore[arg-type]

        def describe(node: CutNode, o: CutOrientation) -> str | None:
            r = node.region
            size = f"{format_length(r.w)} × {format_length(r.h)}"
            if node.kind is NodeKind.PIECE:
                return f"{sheet.placements[node.ref].piece.label} ({size})"  # type: ignore[index]
            if node.kind is NodeKind.EDGE:
                return "Refilado"
            if node.kind is NodeKind.OFFCUT:
                off = by_rect[r]
                if off.status is OffcutStatus.REUSABLE:
                    return f"Retazo {off.label} ({size})"
                return f"Desperdicio ({size})"
            if node.label == "Placa":  # el refilado no «libera» la placa
                return None
            return f"{node.label} ({format_length(r.w if o is V else r.h)} mm)"

        nodes: list[CutNode] = []
        queue = deque([tree.root] if tree.root.kind is NodeKind.CUT else [])
        while queue:
            node = queue.popleft()
            nodes.append(node)
            queue.extend(_execution_order(node.children))
        nodes.sort(key=lambda n: n.level)

        cuts: list[Cut] = []
        for node in nodes:
            o, r = node.orientation, node.region
            assert o is not None
            begin, end = _span(r, o)
            along, length = (r.y, r.h) if o is V else (r.x, r.w)
            last = len(node.positions) - 1
            lo = begin
            for i, p in enumerate(node.positions):
                # Cada corte libera la franja anterior; el último, también la siguiente.
                hi = end if i == last else p
                released = [
                    text
                    for c in node.children
                    if lo <= _span(c.region, o)[0] and _span(c.region, o)[1] <= hi
                    if (text := describe(c, o)) is not None
                ]
                cuts.append(
                    Cut(
                        order=len(cuts) + 1,
                        level=node.level,
                        orientation=o,
                        position=p,
                        start=along,
                        length=length,
                        fence_distance=max(p - lo, 0),
                        is_trim=node.level == 0,
                        resulting=tuple(released),
                        kerf=max(0, min(p + k, end) - max(p, lo)),
                        region=node.label,
                    )
                )
                lo = p + k
        return cuts


# --------------------------------------------------------------------------- utilidades


def plan_result(result: OptimizationResult, material_id: int | None = None) -> OptimizationResult:
    """Añade el plan de corte y los retazos a cada placa del resultado."""
    planner = CuttingPlanner(result.params, material_id)
    return replace(result, sheets=tuple(planner.plan_sheet(s) for s in result.sheets))


def format_plan(sheet: SheetLayout, title: str = "") -> str:
    """Secuencia legible para el operario (docs/04-plan-de-corte-fisico.md §4.3)."""
    plan = sheet.cut_plan
    head = f"PLACA {sheet.index + 1}"
    if title:
        head += f" — {title}"
    lines = [f"{head} ({format_length(sheet.width)} × {format_length(sheet.height)})"]
    if plan is None:
        return lines[0]
    if plan.mode is CutMode.CNC:
        lines.append("Corte en CNC: la distribución no es guillotinable.")
        lines += [
            f"  {c.label}: x = {format_length(c.x)}  y = {format_length(c.y)}  "
            f"{format_length(c.width)} × {format_length(c.height)} mm"
            for c in plan.contours
        ]
        return "\n".join(lines)
    for c in plan.cuts:
        stage = "refilado" if c.is_trim else f"nivel {c.level}"
        axis = "x" if c.orientation is V else "y"
        line = (
            f"CORTE {c.order:<3} [{stage}]".ljust(22)
            + f"{c.orientation.value:<11} {axis} = {format_length(c.position):<8} "
            + f"longitud {format_length(c.length):>6} mm   "
            + f"tope {format_length(c.fence_distance)} mm"
        )
        if c.resulting:
            line += "   → " + ", ".join(c.resulting)
        lines.append(line)
    return "\n".join(lines)
