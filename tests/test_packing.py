"""Packers individuales, descomposición guillotina, espacio de empaquetado y puntuación."""

import random

import pytest

from models.parametros import CuttingParameters
from models.pieza import PieceSpec
from models.placa import PlateFormat
from models.resultado import SheetSource
from models.retazo import Offcut, OffcutStatus
from optimization.guillotine import decompose, is_guillotine
from optimization.packing import GuillotinePacker, MaxRectsPacker, PackerConfig, ShelfPacker
from optimization.scoring import Score
from optimization.space import BinSpec, lower_bound
from utils.geometry import Rect

ANY = (False, True)


def all_packers(w, h):
    for sel in GuillotinePacker.SELECTIONS:
        for split in GuillotinePacker.SPLITS:
            for merge in (True, False):
                yield GuillotinePacker(w, h, sel, split, merge)
    for heur in MaxRectsPacker.HEURISTICS:
        yield MaxRectsPacker(w, h, heur)
    yield ShelfPacker(w, h)


@pytest.mark.parametrize("seed", range(5))
def test_packers_never_overlap_or_overflow(seed):
    rng = random.Random(seed)
    sizes = [(rng.randint(5, 40), rng.randint(5, 40)) for _ in range(40)]
    for packer in all_packers(100, 120):
        for w, h in sizes:
            cand = packer.find(w, h, ANY)
            if cand is not None:
                packer.place(cand)
        bounds = Rect(0, 0, 100, 120)
        for i, a in enumerate(packer.used):
            assert bounds.contains(a), type(packer).__name__
            for b in packer.used[i + 1 :]:
                assert not a.intersects(b), type(packer).__name__
        assert len(packer.used) > 5


def test_packer_rejects_piece_that_does_not_fit():
    for packer in all_packers(100, 100):
        assert packer.find(101, 10, (False,)) is None
        assert packer.find(10, 101, ANY) is None
        assert packer.find(101, 50, ANY) is None  # girada: 50 × 101, tampoco
        assert packer.find(60, 30, (True,)).rotated


def test_guillotine_without_merge_is_always_guillotinable():
    rng = random.Random(3)
    for sel in GuillotinePacker.SELECTIONS:
        for split in GuillotinePacker.SPLITS:
            packer = GuillotinePacker(1000, 1000, sel, split, merge=False)
            for _ in range(60):
                c = packer.find(rng.randint(30, 300), rng.randint(30, 300), ANY)
                if c:
                    packer.place(c)
            assert is_guillotine(packer.used, Rect(0, 0, 1000, 1000), 0)


def test_maxrects_free_rects_are_maximal_and_disjoint_from_used():
    packer = MaxRectsPacker(100, 100)
    for w, h in [(40, 30), (20, 50), (35, 35), (10, 10)]:
        packer.place(packer.find(w, h, ANY))
    for free in packer.free:
        assert all(not free.intersects(u) for u in packer.used)
        assert not any(o != free and o.contains(free) for o in packer.free)


def test_unknown_configuration():
    with pytest.raises(ValueError):
        GuillotinePacker(10, 10, "zzz")
    with pytest.raises(ValueError):
        MaxRectsPacker(10, 10, "zzz")
    assert PackerConfig("guillotine", "baf", "slas").name == "guillotine-baf-slas"


# ---------------------------------------------------------------- guillotina


def test_decompose_two_pieces_side_by_side():
    rects = [Rect(0, 0, 50, 100), Rect(53, 0, 47, 100)]
    d = decompose(rects, Rect(0, 0, 100, 100), kerf=3)
    assert d is not None
    assert d.cut_count == 1 and d.leftovers == []


def test_decompose_trims_leftover_into_one_big_offcut():
    rects = [Rect(0, 0, 30, 30), Rect(0, 33, 30, 30)]  # columna a la izquierda
    d = decompose(rects, Rect(0, 0, 100, 100), kerf=3)
    assert d.largest_leftover_area == (100 - 33) * 100  # franja derecha entera


def test_pieces_closer_than_kerf_are_not_separable():
    rects = [Rect(0, 0, 50, 100), Rect(52, 0, 48, 100)]  # hueco 2 < kerf 3
    assert not is_guillotine(rects, Rect(0, 0, 100, 100), 3)
    assert is_guillotine(rects, Rect(0, 0, 100, 100), 2)


def test_pinwheel_is_not_guillotine():
    s = 100
    pinwheel = [
        Rect(0, 0, 2 * s, s),
        Rect(2 * s, 0, s, 2 * s),
        Rect(s, 2 * s, 2 * s, s),
        Rect(0, s, s, 2 * s),
        Rect(s, s, s, s),
    ]
    assert not is_guillotine(pinwheel, Rect(0, 0, 3 * s, 3 * s), 0)


def test_decompose_counts_cuts_and_leftovers_cover_region():
    rects = [Rect(10, 10, 40, 20), Rect(53, 10, 40, 20), Rect(10, 33, 83, 30)]
    region = Rect(0, 0, 120, 100)
    d = decompose(rects, region, kerf=3)
    assert d is not None
    pieces_area = sum(r.area for r in rects)
    leftovers = d.leftovers
    for i, a in enumerate(leftovers):
        assert region.contains(a)
        assert all(not a.intersects(r) for r in rects)
        assert all(not a.intersects(b) for b in leftovers[i + 1 :])
    assert pieces_area + sum(r.area for r in leftovers) < region.area  # el resto es kerf
    assert d.cut_count >= 2


# ---------------------------------------------------------------- espacio y puntuación


def test_bin_packing_size_and_lower_bound():
    plate = PlateFormat.from_mm("P", 1830, 2820, 18)
    params = CuttingParameters()
    b = BinSpec.from_plate(plate, params)
    assert b.packing_size(32) == (18300 - 200 + 32, 28200 - 200 + 32)
    pieces = PieceSpec.from_mm("Hoja", 3, 1810, 2800, 18).expand()
    assert lower_bound(pieces, b, 32) == 3
    assert lower_bound([], b, 32) == 0


def test_offcut_bin_trim_flag():
    params = CuttingParameters()
    clean = BinSpec.from_offcut(Offcut(5000, 4000, 180, OffcutStatus.IN_STOCK), params, None)
    dirty = BinSpec.from_offcut(
        Offcut(5000, 4000, 180, OffcutStatus.IN_STOCK, needs_trim=True), params, None
    )
    assert clean.margin == 0 and dirty.margin == params.edge_margin
    assert clean.source is SheetSource.OFFCUT and not clean.is_full_plate


def test_score_is_lexicographic():
    better = Score(0, 1, 0, 10**9, -1, 99, 99)
    worse = Score(0, 2, 0, 0, -(10**9), 0, 0)
    uses_offcut = Score(0, 1, -1, 10**9, -1, 99, 99)
    assert uses_offcut < better
    incomplete = Score(1, 1, 0, 0, 0, 0, 0)
    assert better < worse < incomplete
    assert better.scalar() < worse.scalar() < incomplete.scalar()
    assert better.sheets == 1
