from dataclasses import replace

import pytest

from models.parametros import CuttingParameters
from models.pieza import GrainDirection, PieceSpec
from models.placa import PlateFormat, PlateGrain
from models.proyecto import Furniture, Project
from models.validation import (
    IssueCode,
    Severity,
    ValidationFailed,
    ValidationReport,
    validate_parameters,
    validate_piece,
    validate_plate,
    validate_project,
)

PLATE = PlateFormat.from_mm("Melamina", 1830, 2820, 18, material_id=1)
PARAMS = CuttingParameters()


def codes(issues):
    return {i.code for i in issues}


def piece(**kw):
    base = PieceSpec.from_mm("Lateral", 2, 400, 600, 18)
    return replace(base, **kw)


class TestPiece:
    def test_valid_piece_has_no_issues(self):
        assert validate_piece(piece(), PLATE, PARAMS) == []

    def test_zero_quantity(self):
        assert IssueCode.ZERO_QUANTITY in codes(validate_piece(piece(quantity=0)))

    @pytest.mark.parametrize("attr", ["width", "height", "thickness"])
    @pytest.mark.parametrize("value", [0, -10])
    def test_non_positive_dimensions(self, attr, value):
        issues = validate_piece(piece(**{attr: value}))
        assert IssueCode.NON_POSITIVE_DIMENSION in codes(issues)
        assert any(i.field == attr for i in issues)

    def test_empty_name(self):
        assert IssueCode.EMPTY_NAME in codes(validate_piece(piece(name="  ")))

    def test_thickness_mismatch(self):
        issues = validate_piece(piece(thickness=150), PLATE, PARAMS)
        assert IssueCode.THICKNESS_MISMATCH in codes(issues)
        assert "15 mm" in issues[0].message and "18 mm" in issues[0].message

    def test_material_mismatch_is_only_warning(self):
        issues = validate_piece(piece(material_id=2), PLATE, PARAMS)
        assert codes(issues) == {IssueCode.MATERIAL_MISMATCH}
        assert issues[0].severity is Severity.WARNING

    def test_piece_larger_than_plate(self):
        issues = validate_piece(piece(width=30000), PLATE, PARAMS)  # 3000 mm: ni girada
        assert IssueCode.PIECE_LARGER_THAN_PLATE in codes(issues)

    def test_margin_is_considered(self):
        # 1810 mm cabe justo con margen de 10 mm por lado (1830 − 20); 1811 no
        assert validate_piece(piece(width=18100, can_rotate=False), PLATE, PARAMS) == []
        assert IssueCode.PIECE_LARGER_THAN_PLATE in codes(
            validate_piece(piece(width=18110, can_rotate=False), PLATE, PARAMS)
        )

    def test_fits_only_rotated(self):
        # 2500 × 1000 no cabe derecha en 1810 × 2800, pero girada sí
        long_piece = piece(width=25000, height=10000)
        assert validate_piece(long_piece, PLATE, PARAMS) == []
        issues = validate_piece(replace(long_piece, can_rotate=False), PLATE, PARAMS)
        assert IssueCode.PIECE_LARGER_THAN_PLATE in codes(issues)
        assert "cabría girada" in issues[0].message

    def test_grain_blocks_rotation(self):
        grained_plate = replace(PLATE, grain=PlateGrain.ALONG_HEIGHT)
        long_piece = piece(width=25000, height=10000, grain=GrainDirection.HORIZONTAL)
        # veta horizontal en placa con veta a lo largo del alto → debe girarse: cabe
        assert validate_piece(long_piece, grained_plate, PARAMS) == []
        # veta vertical → no se puede girar: no cabe
        vertical = replace(long_piece, grain=GrainDirection.VERTICAL)
        assert IssueCode.PIECE_LARGER_THAN_PLATE in codes(
            validate_piece(vertical, grained_plate, PARAMS)
        )

    def test_too_big_message_is_actionable(self):
        grained_plate = replace(PLATE, grain=PlateGrain.ALONG_HEIGHT)
        door = piece(name="Puerta", width=4820, height=29000, grain=GrainDirection.VERTICAL)
        [issue] = validate_piece(door, grained_plate, PARAMS)
        assert issue.message.startswith(
            "La pieza «Puerta» (482 × 2900 mm) no cabe en la placa 1830 × 2820 con la veta vertical"
        )
        assert issue.message.endswith("reduzca el alto")

    @pytest.mark.parametrize(
        ("changes", "advice"),
        [
            ({"grain": GrainDirection.VERTICAL}, "cambie la veta a «Indiferente»"),
            ({"fixed_orientation": True}, "quite la orientación fija"),
            ({"can_rotate": False}, "permita girar la pieza"),
        ],
    )
    def test_too_big_message_says_what_blocks_rotation(self, changes, advice):
        grained_plate = replace(PLATE, grain=PlateGrain.ALONG_HEIGHT)
        long_piece = piece(width=25000, height=10000, **changes)
        [issue] = [
            i
            for i in validate_piece(long_piece, grained_plate, PARAMS)
            if i.code is IssueCode.PIECE_LARGER_THAN_PLATE
        ]
        assert f"cabría girada: {advice} o reduzca el ancho" in issue.message

    def test_too_big_message_mentions_global_rotation_switch(self):
        params = replace(PARAMS, allow_rotation=False)
        [issue] = validate_piece(piece(width=25000, height=10000), PLATE, params)
        assert "«Permitir rotación de piezas» en PARÁMETROS" in issue.message

    def test_grain_conflict_warning_with_fixed_orientation(self):
        grained_plate = replace(PLATE, grain=PlateGrain.ALONG_HEIGHT)
        p = piece(grain=GrainDirection.HORIZONTAL, fixed_orientation=True)
        issues = validate_piece(p, grained_plate, PARAMS)
        assert codes(issues) == {IssueCode.GRAIN_CONFLICT}

    def test_location_is_propagated(self):
        issues = validate_piece(piece(quantity=0), location=(1, 3))
        assert issues[0].location == (1, 3)


class TestParameters:
    def test_defaults_ok(self):
        assert validate_parameters(PARAMS, PLATE) == []

    @pytest.mark.parametrize("kerf", [-1, 101])
    def test_invalid_kerf(self, kerf):
        assert IssueCode.INVALID_KERF in codes(validate_parameters(replace(PARAMS, kerf=kerf)))

    def test_kerf_zero_and_max_allowed(self):
        assert validate_parameters(replace(PARAMS, kerf=0)) == []
        assert validate_parameters(replace(PARAMS, kerf=100)) == []

    def test_negative_margin_and_spacing(self):
        found = codes(validate_parameters(replace(PARAMS, edge_margin=-1, extra_spacing=-1)))
        assert {IssueCode.INVALID_MARGIN, IssueCode.INVALID_SPACING} <= found

    def test_margin_too_large(self):
        # margen de 915 mm por lado anula los 1830 mm de ancho
        found = codes(validate_parameters(replace(PARAMS, edge_margin=9150), PLATE))
        assert IssueCode.MARGIN_TOO_LARGE in found
        assert validate_parameters(replace(PARAMS, edge_margin=9140), PLATE) == []


def test_validate_plate():
    assert validate_plate(PLATE) == []
    bad = PlateFormat("", 0, 100, -1)
    assert codes(validate_plate(bad)) == {IssueCode.EMPTY_NAME, IssueCode.NON_POSITIVE_DIMENSION}


class TestProject:
    def test_valid_project(self):
        project = Project("Mesita", furniture=[Furniture("Mesita", [piece()])])
        report = validate_project(project, PLATE)
        assert report.is_ok and report.issues == []

    def test_missing_plate_and_pieces(self):
        report = validate_project(Project("Vacío", furniture=[Furniture("Vacío")]), None)
        assert {IssueCode.NO_PLATE_SELECTED, IssueCode.NO_PIECES} <= report.codes()
        assert report.has_errors

    def test_issues_located_per_piece(self):
        project = Project(
            "P", furniture=[Furniture("A", [piece()]), Furniture("B", [piece(), piece(quantity=0)])]
        )
        report = validate_project(project, PLATE)
        assert [i.location for i in report.errors] == [(1, 1)]


def test_validation_failed_message():
    report = ValidationReport(validate_piece(piece(quantity=0)))
    error = ValidationFailed(report)
    assert "cantidad" in str(error) and error.report is report
