"""Kerf, margen y separación adicional: límites exactos en décimas de mm."""

import pytest

from tests.helpers import params_mm, piece, plate_mm, run
from utils.units import mm_to_internal


def two_side_by_side(plate_w, kerf="3.2", margin="0", spacing="0"):
    """Dos piezas de 500 × 600 que no pueden girarse ni apilarse (placa de 600 + márgenes)."""
    plate_h = 600 + 2 * int(margin)
    return run(
        [piece("P", 2, 500, 600, can_rotate=False)],
        plate_mm(plate_w, plate_h),
        params_mm(kerf, margin, spacing),
    )


@pytest.mark.parametrize(
    ("plate_w", "kerf", "margin", "spacing", "sheets"),
    [
        ("1003.2", "3.2", "0", "0", 1),  # 500 + 3,2 + 500
        ("1003.1", "3.2", "0", "0", 2),
        ("1000", "0", "0", "0", 1),  # sin kerf, pegadas
        ("1023.2", "3.2", "10", "0", 1),  # 10 + 500 + 3,2 + 500 + 10
        ("1023.1", "3.2", "10", "0", 2),
        ("1004.2", "3.2", "0", "1", 1),  # kerf + 1 mm de separación extra
        ("1004.1", "3.2", "0", "1", 2),
        ("1004.4", "4.4", "0", "0", 1),  # disco más ancho
        ("1004.3", "4.4", "0", "0", 2),
    ],
)
def test_exact_limits(plate_w, kerf, margin, spacing, sheets):
    assert two_side_by_side(plate_w, kerf, margin, spacing).sheets_count == sheets


def test_coordinates_match_workshop_example():
    """Ejemplo del doc 04: margen 10, kerf 3,2 → segunda pieza en X = 513,2 mm."""
    result = two_side_by_side("1023.2", "3.2", "10")
    xs = sorted(p.x for p in result.placements)
    assert xs == [mm_to_internal(10), mm_to_internal("513.2")]
    assert all(p.y == mm_to_internal(10) for p in result.placements)


def test_all_pairs_separated_by_at_least_kerf():
    kerf = mm_to_internal("3.2")
    result = run(
        [piece(f"P{i}", 3, 200 + 30 * i, 150 + 20 * i) for i in range(8)], plate_mm(1830, 2820)
    )
    for sheet in result.sheets:
        rects = [p.rect for p in sheet.placements]
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                assert rects[i].separation(rects[j]) >= kerf


def test_kerf_eats_capacity():
    """Tiras de 100 mm en 1000 mm: sin kerf caben 10, con 3,2 mm de kerf solo 9."""
    specs = [piece("Tira", 10, 100, 1000, can_rotate=False)]
    assert run(specs, plate_mm(1000, 1000), params_mm("0", "0")).sheets_count == 1
    with_kerf = run(specs, plate_mm(1000, 1000), params_mm("3.2", "0"))
    assert with_kerf.sheets_count == 2
    assert max(len(s.placements) for s in with_kerf.sheets) == 9
