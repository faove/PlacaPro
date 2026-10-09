"""Exportadores: PDF (páginas), CSV (filas y valores), SVG y registro."""

import csv
import re
from datetime import datetime
from pathlib import Path

import pytest

from exporters import EXPORTERS, ExportContext, get_exporter, load_exporters, register
from exporters.csv_exporter import SEQUENCE_TITLE, csv_paths
from exporters.pdf_exporter import ROW_HEIGHT, Table, paginate
from models.pieza import PieceCategory
from models.proyecto import Furniture, Project
from services.report_service import ReportService, safe_filename
from tests.helpers import piece
from tests.test_diagram import multi_sheet_result
from tests.test_optimization_service import demo
from utils.units import Unit, format_length

pytestmark = pytest.mark.ui  # PDF y SVG usan Qt


def pdf_page_count(path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-z])", path.read_bytes()))


@pytest.fixture(scope="module")
def result():
    return multi_sheet_result()


@pytest.fixture
def context(result, qapp):
    pieces = [
        piece("Lateral", 2, 600, 700, category=PieceCategory.LATERAL),
        piece("Tapa", 3, 400, 300, category=PieceCategory.TAPA),
    ]
    project = Project("Placard; «test»", furniture=[Furniture("Placard", pieces)])
    return ExportContext(
        project=project,
        result=result,
        pieces=tuple(("Placard", p) for p in pieces),
        generated_at=datetime(2026, 10, 9, 12, 0),
    )


def read_csv(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 con BOM para Excel
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f, delimiter=";"))


def test_registry_and_menu_order():
    ids = [e.id for e in load_exporters()]
    assert ids[:3] == ["pdf", "csv", "svg"]
    assert load_exporters() == load_exporters()  # idempotente
    with pytest.raises(LookupError):
        get_exporter("docx")
    with pytest.raises(ValueError):
        register(get_exporter("pdf"))


def test_new_exporter_is_one_class_plus_register(context, tmp_path):
    class TxtExporter:
        id = "txt-test"
        name = "Texto…"
        file_filter = "Texto (*.txt)"
        suffix = ".txt"
        menu_order = 99

        def export(self, ctx, path):
            path.write_text(f"{ctx.result.sheets_count} placas", encoding="utf-8")
            return [path]

    register(TxtExporter())
    try:
        assert load_exporters()[-1].id == "txt-test"
        [out] = get_exporter("txt-test").export(context, tmp_path / "r.txt")
        assert out.read_text(encoding="utf-8").startswith(str(context.result.sheets_count))
    finally:
        del EXPORTERS["txt-test"]


def test_pdf_has_two_pages_plus_one_per_sheet(context, tmp_path):
    [path] = get_exporter("pdf").export(context, tmp_path / "plan.pdf")
    assert path.exists() and path.read_bytes().startswith(b"%PDF")
    assert pdf_page_count(path) == 2 + context.result.sheets_count


def test_pdf_paginates_long_tables(qapp):
    rows = [[str(i)] for i in range(200)]
    table = Table("Larga", ["Nº"], rows, [1])
    height = ROW_HEIGHT * 40
    pages = paginate([[table]], 500, height)
    assert len(pages) > 1
    placed = [p for page in pages for p in page]
    spans = [p.rows for p in placed]
    assert spans[0][0] == 0 and spans[-1][1] == 200
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:], strict=False))
    assert not placed[0].continued and all(p.continued for p in placed[1:])


def test_csv_cut_list_matches_result(context, tmp_path):
    pieces_path, cuts_path = get_exporter("csv").export(context, tmp_path / "plan.csv")
    assert (pieces_path, cuts_path) == csv_paths(tmp_path / "plan.csv")
    assert pieces_path.name == "plan_piezas.csv" and cuts_path.name == "plan_cortes.csv"

    rows = read_csv(cuts_path)
    assert rows[0] == [
        "Nº",
        "Pieza",
        "Ancho (mm)",
        "Alto (mm)",
        "Placa",
        "X (mm)",
        "Y (mm)",
        "Rotación",
    ]
    blank = rows.index([])
    body = rows[1:blank]
    placements = [(s, p) for s in context.result.sheets for p in s.placements]
    assert len(body) == len(placements) == context.result.pieces_count
    for row, (sheet, p) in zip(body, placements, strict=True):
        assert row[1] == p.piece.label
        assert row[2:] == [
            format_length(p.width),
            format_length(p.height),
            str(sheet.index + 1),
            format_length(p.x),
            format_length(p.y),
            "Sí" if p.rotated else "No",
        ]
    assert rows[blank + 1] == [SEQUENCE_TITLE]
    cuts = [c for s in context.result.sheets for c in s.cut_plan.cuts]
    assert len(rows) - (blank + 3) == len(cuts)

    pieces_rows = read_csv(pieces_path)
    assert pieces_rows[1][:4] == ["Placard", "Lateral", "Lateral", "2"]
    assert len(pieces_rows) == 1 + len(context.pieces)


def test_csv_uses_context_unit(context, tmp_path):
    from dataclasses import replace

    ctx = replace(context, unit=Unit.CM)
    _, cuts_path = get_exporter("csv").export(ctx, tmp_path / "cm.csv")
    rows = read_csv(cuts_path)
    p = context.result.sheets[0].placements[0]
    assert rows[0][2] == "Ancho (cm)"
    assert rows[1][2] == format_length(p.width, Unit.CM)
    assert rows[rows.index([SEQUENCE_TITLE]) + 1][4] == "Medida de tope (cm)"


def test_svg_one_file_per_sheet(context, tmp_path):
    paths = get_exporter("svg").export(context, tmp_path / "plan.svg")
    assert len(paths) == context.result.sheets_count
    for path, sheet in zip(paths, context.result.sheets, strict=True):
        text = path.read_text(encoding="utf-8")
        assert path.name == f"plan_placa{sheet.index + 1}.svg"
        assert "<svg" in text and sheet.placements[0].piece.label in text


def test_report_service_exports_demo(db, qapp, tmp_path):
    project = demo(db)
    from services.optimization_service import OptimizationService

    result = OptimizationService(db).optimize(project, time_budget_s=1).result
    reports = ReportService(db)
    context = reports.build_context(project, result)
    assert context.plate is not None and context.material_name(context.plate.material_id)
    assert sum(spec.quantity for _, spec in context.pieces) == 7
    assert reports.default_filename(project, "pdf") == "Mesita de noche - plan de corte.pdf"
    [pdf] = reports.export("pdf", project, result, tmp_path / "demo.pdf")
    assert pdf_page_count(pdf) == 3
    assert len(reports.export("csv", project, result, tmp_path / "demo.csv")) == 2


def test_safe_filename():
    assert safe_filename('Mueble: "A/B"?') == "Mueble_ _A_B_"
    assert safe_filename("  ..  ") == "proyecto"
