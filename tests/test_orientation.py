import pytest

from models.pieza import GrainDirection, PieceSpec
from models.placa import PlateGrain
from optimization.orientation import (
    ORIENTATION_ANY,
    ORIENTATION_AS_DRAWN,
    ORIENTATION_ROTATED,
    allowed_rotations,
    oriented_size,
)

V, H, N = GrainDirection.VERTICAL, GrainDirection.HORIZONTAL, GrainDirection.NONE
PH, PW, PN = PlateGrain.ALONG_HEIGHT, PlateGrain.ALONG_WIDTH, PlateGrain.NONE


def spec(grain=N, can_rotate=True, fixed=False):
    return PieceSpec.from_mm(
        "P", 1, 500, 700, 18, grain=grain, can_rotate=can_rotate, fixed_orientation=fixed
    )


@pytest.mark.parametrize(
    ("grain", "plate_grain", "expected"),
    [
        (V, PH, ORIENTATION_AS_DRAWN),  # veta ya alineada
        (H, PH, ORIENTATION_ROTATED),  # hay que girarla para alinear la veta
        (V, PW, ORIENTATION_ROTATED),
        (H, PW, ORIENTATION_AS_DRAWN),
        (V, PN, ORIENTATION_AS_DRAWN),  # placa lisa: se respeta lo dibujado
        (H, PN, ORIENTATION_AS_DRAWN),
    ],
)
def test_grain_table(grain, plate_grain, expected):
    assert allowed_rotations(spec(grain), plate_grain) == expected


def test_grain_wins_over_rotation_flags():
    # Aunque la rotación esté desactivada, alinear la veta es obligatorio.
    assert (
        allowed_rotations(spec(H, can_rotate=False), PH, allow_rotation=False)
        == ORIENTATION_ROTATED
    )


@pytest.mark.parametrize("plate_grain", [PH, PW, PN])
def test_no_grain_rotation_rules(plate_grain):
    assert allowed_rotations(spec(), plate_grain) == ORIENTATION_ANY
    assert allowed_rotations(spec(can_rotate=False), plate_grain) == ORIENTATION_AS_DRAWN
    assert allowed_rotations(spec(), plate_grain, allow_rotation=False) == ORIENTATION_AS_DRAWN


@pytest.mark.parametrize("grain", [V, H, N])
def test_fixed_orientation_always_as_drawn(grain):
    assert allowed_rotations(spec(grain, fixed=True), PH) == ORIENTATION_AS_DRAWN


def test_oriented_size():
    assert oriented_size(500, 700, False) == (500, 700)
    assert oriented_size(500, 700, True) == (700, 500)
