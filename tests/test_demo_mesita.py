"""Prueba de punta a punta: datos iniciales → optimizar → verificar → plan de corte →
exportar PDF y CSV. Cubre la demo «Mesita de noche» (RF-13) y el ejemplo «Mueble bajo»
de la checklist manual del sprint 7."""

import csv
from collections import Counter

import pytest

from database.seed import DEMO_PROJECT_NAME, seed
from models.pieza import PieceSpec
from models.proyecto import Furniture
from optimization.verification import verify_result
from services.optimization_service import OptimizationService
from services.project_service import ProjectService
from services.report_service import ReportService
from tests.helpers import assert_plan_reconstructs
from tests.test_exporters import pdf_page_count
from utils.units import mm_to_internal

pytestmark = pytest.mark.ui  # el PDF usa Qt

DEMO_PIECES = {
    # nombre: (cantidad, ancho, alto) en mm
    "Lateral": (2, 400, 600),
    "Tapa": (1, 564, 400),
    "Fondo": (1, 564, 600),
    "Puerta": (2, 282, 600),
    "Zócalo": (1, 564, 100),
}

MUEBLE_BAJO = [
    PieceSpec.from_mm("Lateral", 2, 700, 500, 18),
    PieceSpec.from_mm("Tapa/Base", 2, 964, 500, 18),
    PieceSpec.from_mm("Fondo", 1, 964, 664, 18),
    PieceSpec.from_mm("Puerta", 2, 482, 700, 18),
]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f, delimiter=";"))


def optimize_and_check(db, project):
    service = OptimizationService(db)
    prepared = service.prepare(project)
    outcome = service.optimize(project, time_budget_s=2)
    assert outcome.ok and outcome.report.errors == []
    result = outcome.result
    assert not result.unplaced
    # invariantes: márgenes, separación ≥ kerf, medidas exactas, orientación permitida
    assert verify_result(result, prepared.request.pieces, prepared.plate.grain) == []
    for sheet in result.sheets:
        assert_plan_reconstructs(sheet, result.params)
    return prepared, result


def test_demo_mesita_end_to_end(db, qapp, tmp_path):
    seeded = seed(db)
    assert seeded.seeded and seeded.demo_project_id is not None
    project = ProjectService(db).open(seeded.demo_project_id)
    assert project.name == DEMO_PROJECT_NAME

    # datos de la demo según RF-13
    specs = project.all_piece_specs()
    assert {s.name: (s.quantity, s.width_mm, s.height_mm) for s in specs} == DEMO_PIECES
    assert project.params.kerf == mm_to_internal("3.2")
    assert project.params.edge_margin == mm_to_internal(10)
    prepared, result = optimize_and_check(db, project)
    plate = prepared.plate
    assert (plate.width_mm, plate.height_mm, plate.thickness_mm) == (1830, 2820, 18)

    assert result.sheets_count == 1 and result.pieces_count == 7
    assert result.id is not None  # guardado con el proyecto
    sheet = result.sheets[0]
    labels = Counter(p.piece.spec.name for p in sheet.placements)
    assert labels == {name: q for name, (q, _w, _h) in DEMO_PIECES.items()}
    assert 0 < result.utilization < 1

    # exportar PDF (proyecto + resumen + 1 placa) y CSV (piezas y cortes)
    reports = ReportService(db)
    [pdf] = reports.export("pdf", project, result, tmp_path / "mesita.pdf")
    assert pdf.exists() and pdf_page_count(pdf) == 3
    pieces_csv, cuts_csv = reports.export("csv", project, result, tmp_path / "mesita.csv")
    piece_rows = read_csv(pieces_csv)[1:]  # una fila por pieza definida, con su cantidad
    assert {row[1]: int(row[3]) for row in piece_rows} == {
        name: q for name, (q, _w, _h) in DEMO_PIECES.items()
    }
    cut_rows = read_csv(cuts_csv)
    assert len([r for r in cut_rows if r and r[0] == "Secuencia de cortes"]) == 1


def test_mueble_bajo_manual_checklist(db, qapp, tmp_path):
    """Pasos 1–9 de la checklist manual, sin la interfaz."""
    seed(db)
    projects = ProjectService(db)
    plate_id = next(
        p.id
        for p in OptimizationService(db).plates.list()
        if (p.width_mm, p.height_mm, p.thickness_mm) == (1830, 2820, 18)
    )
    project = projects.new_project("Mueble bajo", plate_id)
    project.furniture = [Furniture("Mueble bajo", list(MUEBLE_BAJO))]
    project = projects.save(project)

    _prepared, result = optimize_and_check(db, project)
    assert result.sheets_count == 1 and result.pieces_count == 7

    # X/Y verificables a mano: la primera pieza arranca en el margen (10, 10) y toda
    # pieza a su derecha está al menos un kerf (3,2 mm) más allá de su borde.
    sheet = result.sheets[0]
    margin, kerf = result.params.edge_margin, result.params.kerf
    first = min(sheet.placements, key=lambda p: (p.y, p.x))
    assert (first.x, first.y) == (margin, margin)
    right = [p for p in sheet.placements if p.y == first.y and p.x > first.x]
    if right:
        neighbour = min(right, key=lambda p: p.x)
        assert neighbour.x >= first.x + first.width + kerf

    # desperdicio y retazos coherentes: todo el área queda contada
    offcut_area = sum(o.area for o in sheet.offcuts)
    assert sheet.used_area + sheet.kerf_area + offcut_area == sheet.total_area

    reports = ReportService(db)
    assert reports.export("pdf", project, result, tmp_path / "bajo.pdf")[0].exists()
    assert len(reports.export("csv", project, result, tmp_path / "bajo.csv")) == 2
