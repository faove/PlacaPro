"""Validaciones de dominio con mensajes claros para el usuario.

Las entidades solo comprueban tipos; aquí se aplican las reglas de negocio y se
devuelve un ``ValidationReport`` (nunca se lanza una excepción por un dato inválido).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from models.parametros import CuttingParameters
from models.pieza import GrainDirection, PieceSpec
from models.placa import PlateFormat
from models.proyecto import Project
from optimization.orientation import allowed_rotations, grain_required_rotation, oriented_size
from utils.constants import MAX_KERF_MM
from utils.units import format_length, mm_to_internal

MAX_KERF = mm_to_internal(MAX_KERF_MM)


class Severity(Enum):
    ERROR = "error"
    """Impide optimizar."""
    WARNING = "warning"
    """Se informa pero no bloquea."""


class IssueCode(Enum):
    EMPTY_NAME = "EMPTY_NAME"
    NON_POSITIVE_DIMENSION = "NON_POSITIVE_DIMENSION"
    ZERO_QUANTITY = "ZERO_QUANTITY"
    THICKNESS_MISMATCH = "THICKNESS_MISMATCH"
    MATERIAL_MISMATCH = "MATERIAL_MISMATCH"
    PIECE_LARGER_THAN_PLATE = "PIECE_LARGER_THAN_PLATE"
    GRAIN_CONFLICT = "GRAIN_CONFLICT"
    INVALID_KERF = "INVALID_KERF"
    INVALID_MARGIN = "INVALID_MARGIN"
    MARGIN_TOO_LARGE = "MARGIN_TOO_LARGE"
    INVALID_SPACING = "INVALID_SPACING"
    INVALID_OFFCUT_MINIMUM = "INVALID_OFFCUT_MINIMUM"
    NO_PLATE_SELECTED = "NO_PLATE_SELECTED"
    NO_PIECES = "NO_PIECES"
    UNPLACEABLE_PIECE = "UNPLACEABLE_PIECE"


@dataclass(frozen=True)
class ValidationIssue:
    code: IssueCode
    severity: Severity
    message: str
    field: str | None = None
    """Campo afectado (``"width"``, ``"kerf"``...) para resaltarlo en la UI."""
    location: tuple[int, int] | None = None
    """(índice de mueble, índice de pieza) dentro del proyecto, si aplica."""


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def has_errors(self) -> bool:
        return any(i.severity is Severity.ERROR for i in self.issues)

    @property
    def is_ok(self) -> bool:
        return not self.has_errors

    def codes(self) -> set[IssueCode]:
        return {i.code for i in self.issues}

    def extend(self, issues: Iterable[ValidationIssue]) -> None:
        self.issues.extend(issues)


class ValidationFailed(Exception):
    """La operación se canceló porque la validación encontró errores."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__("; ".join(i.message for i in report.errors) or "Validación fallida")


def _error(code: IssueCode, message: str, **kw: object) -> ValidationIssue:
    return ValidationIssue(code, Severity.ERROR, message, **kw)  # type: ignore[arg-type]


def _warning(code: IssueCode, message: str, **kw: object) -> ValidationIssue:
    return ValidationIssue(code, Severity.WARNING, message, **kw)  # type: ignore[arg-type]


def _mm(value: int) -> str:
    return f"{format_length(value)} mm"


def validate_plate(plate: PlateFormat) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not plate.name.strip():
        issues.append(_error(IssueCode.EMPTY_NAME, "La placa debe tener un nombre", field="name"))
    for attr, label in (("width", "ancho"), ("height", "alto"), ("thickness", "espesor")):
        if getattr(plate, attr) <= 0:
            issues.append(
                _error(
                    IssueCode.NON_POSITIVE_DIMENSION,
                    f"El {label} de la placa debe ser mayor que cero",
                    field=attr,
                )
            )
    return issues


def validate_parameters(
    params: CuttingParameters, plate: PlateFormat | None = None
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not 0 <= params.kerf <= MAX_KERF:
        issues.append(
            _error(
                IssueCode.INVALID_KERF,
                f"El kerf debe estar entre 0 y {_mm(MAX_KERF)} (valor: {_mm(params.kerf)})",
                field="kerf",
            )
        )
    if params.edge_margin < 0:
        issues.append(
            _error(IssueCode.INVALID_MARGIN, "El margen no puede ser negativo", field="edge_margin")
        )
    if params.extra_spacing < 0:
        issues.append(
            _error(
                IssueCode.INVALID_SPACING,
                "La separación entre piezas no puede ser negativa",
                field="extra_spacing",
            )
        )
    for attr in ("min_offcut_width", "min_offcut_height", "min_offcut_area"):
        if getattr(params, attr) < 0:
            issues.append(
                _error(
                    IssueCode.INVALID_OFFCUT_MINIMUM,
                    "Los mínimos de retazo no pueden ser negativos",
                    field=attr,
                )
            )
    if plate is not None and params.edge_margin >= 0:
        if 2 * params.edge_margin >= min(plate.width, plate.height):
            issues.append(
                _error(
                    IssueCode.MARGIN_TOO_LARGE,
                    f"El margen de {_mm(params.edge_margin)} por lado no deja superficie útil "
                    f"en la placa {plate.dimensions_label}",
                    field="edge_margin",
                )
            )
    return issues


def validate_piece(
    spec: PieceSpec,
    plate: PlateFormat | None = None,
    params: CuttingParameters | None = None,
    location: tuple[int, int] | None = None,
) -> list[ValidationIssue]:
    """Valida una pieza; si se indican placa y parámetros, comprueba también que quepa."""
    name = spec.name.strip() or "(sin nombre)"
    issues: list[ValidationIssue] = []
    if not spec.name.strip():
        issues.append(
            _error(
                IssueCode.EMPTY_NAME,
                "La pieza debe tener un nombre",
                field="name",
                location=location,
            )
        )
    if spec.quantity < 1:
        issues.append(
            _error(
                IssueCode.ZERO_QUANTITY,
                f"La pieza «{name}» debe tener cantidad 1 o más",
                field="quantity",
                location=location,
            )
        )
    dims_ok = True
    for attr, label in (("width", "ancho"), ("height", "alto"), ("thickness", "espesor")):
        if getattr(spec, attr) <= 0:
            dims_ok = False
            issues.append(
                _error(
                    IssueCode.NON_POSITIVE_DIMENSION,
                    f"El {label} de la pieza «{name}» debe ser mayor que cero",
                    field=attr,
                    location=location,
                )
            )
    if plate is None:
        return issues

    if spec.thickness > 0 and spec.thickness != plate.thickness:
        issues.append(
            _error(
                IssueCode.THICKNESS_MISMATCH,
                f"La pieza «{name}» es de {_mm(spec.thickness)} pero la placa "
                f"«{plate.name}» es de {_mm(plate.thickness)}",
                field="thickness",
                location=location,
            )
        )
    if (
        spec.material_id is not None
        and plate.material_id is not None
        and spec.material_id != plate.material_id
    ):
        issues.append(
            _warning(
                IssueCode.MATERIAL_MISMATCH,
                f"El material de la pieza «{name}» no coincide con el de la placa «{plate.name}»",
                field="material_id",
                location=location,
            )
        )

    params = params or CuttingParameters()
    if spec.fixed_orientation and grain_required_rotation(spec.grain, plate.grain):
        issues.append(
            _warning(
                IssueCode.GRAIN_CONFLICT,
                f"La pieza «{name}» tiene orientación fija pero su veta no coincide con la "
                "de la placa; se respetará la orientación fija",
                field="grain",
                location=location,
            )
        )

    if dims_ok and 2 * params.edge_margin < min(plate.width, plate.height):
        message = _fit_problem(spec, name, plate, params)
        if message is not None:
            issues.append(
                _error(
                    IssueCode.PIECE_LARGER_THAN_PLATE,
                    message,
                    field="width",
                    location=location,
                )
            )
    return issues


def _rotation_blocker(spec: PieceSpec) -> str:
    """Por qué la pieza no puede girarse (para sugerir qué cambiar)."""
    if spec.fixed_orientation:
        return "quite la orientación fija"
    if spec.grain is not GrainDirection.NONE:
        return "cambie la veta a «Indiferente»"
    if not spec.can_rotate:
        return "permita girar la pieza"
    return "active «Permitir rotación de piezas» en PARÁMETROS"


def _fit_problem(
    spec: PieceSpec, name: str, plate: PlateFormat, params: CuttingParameters
) -> str | None:
    """Mensaje accionable si la pieza no cabe en la superficie útil; ``None`` si cabe."""
    usable = plate.usable_rect(params.edge_margin)
    rotations = allowed_rotations(spec, plate.grain, params.allow_rotation)
    if any(
        w <= usable.w and h <= usable.h
        for w, h in (oriented_size(spec.width, spec.height, r) for r in rotations)
    ):
        return None
    # Medidas de la pieza que sobran, en la orientación en que se colocaría.
    rotated = rotations[0]
    along_plate_width, along_plate_height = ("alto", "ancho") if rotated else ("ancho", "alto")
    w, h = oriented_size(spec.width, spec.height, rotated)
    too_big = [
        d
        for d, over in ((along_plate_width, w > usable.w), (along_plate_height, h > usable.h))
        if over
    ]
    reduce = "reduzca " + " y ".join(f"el {d}" for d in too_big)
    condition = ""
    if len(rotations) == 1 and spec.grain is not GrainDirection.NONE:
        condition = f" con la {spec.grain.label.lower()}"
    fits_rotated = len(rotations) == 1 and all(
        a <= b for a, b in zip(oriented_size(w, h, True), (usable.w, usable.h), strict=True)
    )
    advice = f"cabría girada: {_rotation_blocker(spec)} o {reduce}" if fits_rotated else reduce
    return (
        f"La pieza «{name}» ({spec.dimensions_label} mm) no cabe en la placa "
        f"{format_length(plate.width)} × {format_length(plate.height)}{condition} "
        f"(superficie útil {format_length(usable.w)} × {format_length(usable.h)} mm con "
        f"margen de {_mm(params.edge_margin)}); {advice}"
    )


def validate_project(project: Project, plate: PlateFormat | None) -> ValidationReport:
    """Validación completa antes de optimizar."""
    report = ValidationReport()
    if not project.name.strip():
        report.issues.append(
            _error(IssueCode.EMPTY_NAME, "El proyecto debe tener un nombre", field="name")
        )
    if plate is None:
        report.issues.append(
            _error(IssueCode.NO_PLATE_SELECTED, "Seleccione una placa para el proyecto")
        )
    else:
        report.extend(validate_plate(plate))
    report.extend(validate_parameters(project.params, plate))
    if not project.all_piece_specs():
        report.issues.append(_error(IssueCode.NO_PIECES, "El proyecto no tiene piezas"))
    for fi, item in enumerate(project.furniture):
        for pi, spec in enumerate(item.pieces):
            report.extend(validate_piece(spec, plate, project.params, location=(fi, pi)))
    return report
