"""Función de puntuación de una solución (menor = mejor).

El enunciado propone ``placas × 1.000.000 + desperdicio + cortes × penalización``. Con un
número fijo de placas el desperdicio total es constante (área de placas − área de
piezas), así que ese término no distingue entre soluciones. Por eso se usa una
comparación **lexicográfica** (docs/03-algoritmo-de-optimizacion.md §7):

0. piezas sin colocar (una solución incompleta nunca gana a una completa);
1. placas enteras usadas (nuevas + inventario);
2. retazos de stock aprovechados (más es mejor: ahorran espacio en placas nuevas);
3. área ocupada en la placa menos llena (piezas concentradas → sobrante grande);
4. sobrante cortable más grande (cuanto mayor, mejor: más reutilizable);
5. número de cortes;
6. longitud total de corte.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Score:
    unplaced: int
    full_sheets: int
    neg_offcut_sheets: int
    least_filled_area: int
    neg_largest_leftover: int
    cut_count: int
    cut_length: int

    @property
    def sheets(self) -> int:
        return self.full_sheets - self.neg_offcut_sheets

    def as_tuple(self) -> tuple[int, ...]:
        return (
            self.unplaced,
            self.full_sheets,
            self.neg_offcut_sheets,
            self.least_filled_area,
            self.neg_largest_leftover,
            self.cut_count,
            self.cut_length,
        )

    def scalar(self, cut_penalty: int = 1_000_000) -> int:
        """Equivalente escalar orientativo (placas × 10¹⁸ + …), para mostrar y comparar."""
        return (
            self.unplaced * 10**20
            + self.full_sheets * 10**18
            + self.neg_offcut_sheets * 10**16
            + self.least_filled_area
            + self.cut_count * cut_penalty
        )
