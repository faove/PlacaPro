"""Geometría rectangular exacta en unidades internas (enteros, décimas de mm).

Sistema de coordenadas: origen en la esquina superior izquierda de la placa,
X hacia la derecha, Y hacia abajo (convención de taller y de Qt).
"""

from __future__ import annotations

from dataclasses import dataclass


def _check_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} debe ser int (unidades internas), no {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class Rect:
    """Rectángulo alineado a los ejes. ``w`` y ``h`` no pueden ser negativos."""

    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        for name in ("x", "y", "w", "h"):
            _check_int(name, getattr(self, name))
        if self.w < 0 or self.h < 0:
            raise ValueError(f"Dimensiones negativas: {self.w} × {self.h}")

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def is_empty(self) -> bool:
        return self.w == 0 or self.h == 0

    def intersects(self, other: Rect) -> bool:
        """True si comparten área positiva. Tocarse por un borde NO es intersección."""
        return (
            self.x < other.right
            and other.x < self.right
            and self.y < other.bottom
            and other.y < self.bottom
        )

    def intersection(self, other: Rect) -> Rect | None:
        """Rectángulo común o ``None`` si no comparten área."""
        if not self.intersects(other):
            return None
        x, y = max(self.x, other.x), max(self.y, other.y)
        return Rect(x, y, min(self.right, other.right) - x, min(self.bottom, other.bottom) - y)

    def contains(self, other: Rect) -> bool:
        """True si ``other`` está completamente dentro (bordes incluidos)."""
        return (
            self.x <= other.x
            and self.y <= other.y
            and other.right <= self.right
            and other.bottom <= self.bottom
        )

    def separation(self, other: Rect) -> int:
        """Separación de corte entre dos rectángulos.

        Es el mayor de los huecos horizontal y vertical. Para que una sierra pase
        entre dos piezas basta con que estén separadas al menos ``kerf`` en uno de
        los dos ejes. Un valor negativo indica solape; 0 indica que se tocan.
        """
        h_gap = max(other.x - self.right, self.x - other.right)
        v_gap = max(other.y - self.bottom, self.y - other.bottom)
        return max(h_gap, v_gap)

    def translated(self, dx: int, dy: int) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def rotated(self) -> Rect:
        """Mismo origen con ancho y alto intercambiados (giro de 90°)."""
        return Rect(self.x, self.y, self.h, self.w)


def fits(w: int, h: int, container_w: int, container_h: int) -> bool:
    """True si un rectángulo ``w × h`` cabe sin girar en ``container_w × container_h``."""
    return w <= container_w and h <= container_h


def subtract(free: Rect, used: Rect) -> list[Rect]:
    """Resta ``used`` de ``free`` devolviendo los rectángulos libres **maximales**.

    Es la operación de partición de MaxRects: hasta cuatro rectángulos (izquierda,
    derecha, arriba, abajo) que pueden solaparse entre sí y cuya unión es exactamente
    ``free − used``. Si no se intersecan devuelve ``[free]``.
    """
    if not free.intersects(used):
        return [free]
    parts: list[Rect] = []
    if used.x > free.x:
        parts.append(Rect(free.x, free.y, used.x - free.x, free.h))
    if used.right < free.right:
        parts.append(Rect(used.right, free.y, free.right - used.right, free.h))
    if used.y > free.y:
        parts.append(Rect(free.x, free.y, free.w, used.y - free.y))
    if used.bottom < free.bottom:
        parts.append(Rect(free.x, used.bottom, free.w, free.bottom - used.bottom))
    return parts


def prune_contained(rects: list[Rect]) -> list[Rect]:
    """Elimina rectángulos vacíos y los contenidos en otro (deja uno de cada duplicado)."""
    result: list[Rect] = []
    candidates = [r for r in rects if not r.is_empty]
    for i, r in enumerate(candidates):
        dominated = any(
            j != i and o.contains(r) and (o != r or j < i) for j, o in enumerate(candidates)
        )
        if not dominated:
            result.append(r)
    return result
