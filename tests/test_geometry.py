import pytest
from hypothesis import given
from hypothesis import strategies as st

from utils.geometry import Rect, fits, prune_contained, subtract


class TestRect:
    def test_properties(self):
        r = Rect(100, 200, 5000, 7000)
        assert (r.right, r.bottom, r.area) == (5100, 7200, 35_000_000)
        assert not r.is_empty
        assert Rect(0, 0, 0, 10).is_empty

    def test_rejects_negative_and_non_int(self):
        with pytest.raises(ValueError):
            Rect(0, 0, -1, 10)
        with pytest.raises(TypeError):
            Rect(0, 0, 10.0, 10)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Rect(0, 0, True, 10)  # type: ignore[arg-type]

    def test_adjacent_rects_do_not_intersect(self):
        a = Rect(0, 0, 100, 100)
        assert not a.intersects(Rect(100, 0, 100, 100))  # toca por la derecha
        assert not a.intersects(Rect(0, 100, 100, 100))  # toca por abajo
        assert not a.intersects(Rect(100, 100, 10, 10))  # toca por la esquina
        assert a.intersection(Rect(100, 0, 10, 10)) is None

    def test_overlap(self):
        a, b = Rect(0, 0, 100, 100), Rect(50, 60, 100, 100)
        assert a.intersects(b) and b.intersects(a)
        assert a.intersection(b) == Rect(50, 60, 50, 40)

    def test_contains(self):
        outer = Rect(0, 0, 100, 100)
        assert outer.contains(Rect(0, 0, 100, 100))
        assert outer.contains(Rect(10, 10, 20, 20))
        assert not outer.contains(Rect(90, 90, 20, 5))

    def test_separation(self):
        a = Rect(0, 0, 5000, 7000)
        kerf = 32
        assert a.separation(Rect(5032, 0, 5000, 7000)) == kerf  # al lado, con kerf
        assert a.separation(Rect(0, 7032, 5000, 100)) == kerf  # debajo, con kerf
        assert a.separation(Rect(5000, 0, 10, 10)) == 0  # se tocan
        assert a.separation(Rect(4990, 0, 10, 10)) < 0  # se solapan
        # en diagonal: vale el mayor hueco (la sierra pasa por ese eje)
        assert a.separation(Rect(5010, 7100, 10, 10)) == 100
        assert a.separation(Rect(5032, 0, 10, 10)) == Rect(5032, 0, 10, 10).separation(a)

    def test_translate_and_rotate(self):
        r = Rect(10, 20, 300, 400)
        assert r.translated(5, -5) == Rect(15, 15, 300, 400)
        assert r.rotated() == Rect(10, 20, 400, 300)


def test_fits():
    assert fits(18300, 28200, 18300, 28200)
    assert not fits(18301, 100, 18300, 28200)
    assert not fits(28200, 18300, 18300, 28200)  # solo cabría girado


class TestSubtract:
    def test_no_intersection_returns_original(self):
        free = Rect(0, 0, 100, 100)
        assert subtract(free, Rect(200, 200, 10, 10)) == [free]

    def test_corner_placement_gives_two_maximal_rects(self):
        parts = subtract(Rect(0, 0, 100, 100), Rect(0, 0, 40, 30))
        assert sorted(parts, key=lambda r: (r.x, r.y)) == [
            Rect(0, 30, 100, 70),
            Rect(40, 0, 60, 100),
        ]

    def test_center_placement_gives_four(self):
        parts = subtract(Rect(0, 0, 100, 100), Rect(40, 40, 20, 20))
        assert len(parts) == 4

    def test_full_cover_leaves_nothing(self):
        assert subtract(Rect(0, 0, 100, 100), Rect(-10, -10, 200, 200)) == []

    @given(
        st.integers(0, 50),
        st.integers(0, 50),
        st.integers(1, 60),
        st.integers(1, 60),
    )
    def test_union_equals_free_minus_used(self, ux, uy, uw, uh):
        free, used = Rect(0, 0, 60, 60), Rect(ux, uy, uw, uh)
        parts = subtract(free, used)
        for p in parts:
            assert free.contains(p)
            assert not p.intersects(used)
        # muestreo de celdas unitarias: cada celda libre está cubierta por alguna parte
        for cx in range(0, 60, 3):
            for cy in range(0, 60, 3):
                cell = Rect(cx, cy, 1, 1)
                if not cell.intersects(used):
                    assert any(p.contains(cell) for p in parts)


def test_prune_contained():
    big, small, other = Rect(0, 0, 100, 100), Rect(10, 10, 10, 10), Rect(200, 0, 10, 10)
    pruned = prune_contained([big, small, other, Rect(0, 0, 100, 100), Rect(5, 5, 0, 3)])
    assert pruned == [big, other]
