from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from utils.units import (
    LengthError,
    Unit,
    area_internal_to_m2,
    format_area_m2,
    format_length,
    internal_to_mm,
    mm_to_internal,
    parse_length,
    to_unit,
)


class TestParseLength:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("1830", Decimal("1830")),
            ("1830,5", Decimal("1830.5")),
            ("1830.5", Decimal("1830.5")),
            ("3.2", Decimal("3.2")),
            ("  3,2  ", Decimal("3.2")),
            ("0.1", Decimal("0.1")),
        ],
    )
    def test_valid_mm(self, text, expected):
        assert parse_length(text) == expected

    @pytest.mark.parametrize("text", ["3.25", "0.05", "1830,55"])
    def test_rejects_more_than_one_decimal(self, text):
        with pytest.raises(LengthError, match="decimal"):
            parse_length(text)

    @pytest.mark.parametrize("text", ["-1", "-0.1"])
    def test_rejects_negative(self, text):
        with pytest.raises(LengthError, match="negativa"):
            parse_length(text)

    @pytest.mark.parametrize("text", ["abc", "", "   ", "1,2,3", "nan", "inf"])
    def test_rejects_garbage(self, text):
        with pytest.raises(LengthError):
            parse_length(text)

    def test_zero_rejected_by_default_but_allowed_for_margins(self):
        with pytest.raises(LengthError, match="mayor que cero"):
            parse_length("0")
        assert parse_length("0", allow_zero=True) == 0

    def test_input_in_cm_and_m(self):
        assert parse_length("183", Unit.CM) == Decimal("1830")
        assert parse_length("0,32", Unit.CM) == Decimal("3.2")
        assert parse_length("2,82", Unit.M) == Decimal("2820")
        assert parse_length("0.0001", Unit.M) == Decimal("0.1")

    def test_precision_checked_after_unit_conversion(self):
        # 0,001 cm = 0,01 mm -> demasiado fino
        with pytest.raises(LengthError):
            parse_length("0.001", Unit.CM)

    def test_float_rejected(self):
        with pytest.raises(TypeError):
            parse_length(3.2)  # type: ignore[arg-type]


class TestInternalConversion:
    @pytest.mark.parametrize(
        ("mm", "internal"),
        [
            (Decimal("1830"), 18300),
            (Decimal("3.2"), 32),
            ("2820", 28200),
            (10, 100),
            (Decimal("0.1"), 1),
        ],
    )
    def test_round_trip(self, mm, internal):
        assert mm_to_internal(mm) == internal
        assert internal_to_mm(internal) == Decimal(str(mm))

    def test_rejects_sub_tenth(self):
        with pytest.raises(LengthError):
            mm_to_internal(Decimal("3.25"))

    def test_rejects_float(self):
        with pytest.raises(TypeError):
            mm_to_internal(3.2)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            internal_to_mm(3.0)  # type: ignore[arg-type]

    def test_no_float_accumulation(self):
        # Con floats: 0.1 + 0.2 != 0.3 y 3.2 * 3 == 9.600000000000001
        kerf = mm_to_internal("3.2")
        assert kerf * 3 == mm_to_internal("9.6")
        assert mm_to_internal("0.1") + mm_to_internal("0.2") == mm_to_internal("0.3")
        # 500 + kerf + 500 = 1003,2 mm exactos
        assert internal_to_mm(mm_to_internal(500) * 2 + kerf) == Decimal("1003.2")

    @given(st.integers(min_value=0, max_value=10**8))
    def test_round_trip_property(self, internal):
        assert mm_to_internal(internal_to_mm(internal)) == internal

    def test_to_unit(self):
        assert to_unit(18300, Unit.CM) == Decimal("183")
        assert to_unit(18300, Unit.M) == Decimal("1.83")


class TestFormatting:
    @pytest.mark.parametrize(
        ("internal", "unit", "expected"),
        [
            (18300, Unit.MM, "1830"),
            (32, Unit.MM, "3,2"),
            (5132, Unit.MM, "513,2"),
            (18300, Unit.CM, "183"),
            (32, Unit.CM, "0,32"),
            (18305, Unit.M, "1,8305"),
            (28200, Unit.M, "2,82"),
            (0, Unit.MM, "0"),
        ],
    )
    def test_format_length(self, internal, unit, expected):
        assert format_length(internal, unit) == expected

    def test_format_with_unit_and_fixed_decimals(self):
        assert format_length(18300, Unit.MM, with_unit=True) == "1830 mm"
        assert format_length(18300, Unit.MM, decimals=1, trim=False) == "1830,0"
        assert format_length(32, Unit.MM, decimal_sep=".") == "3.2"

    def test_area(self):
        plate = mm_to_internal(1830) * mm_to_internal(2820)
        assert area_internal_to_m2(plate) == Decimal("5.1606")
        assert format_area_m2(plate) == "5,16 m²"
        assert format_area_m2(plate, decimals=4, with_unit=False) == "5,1606"
