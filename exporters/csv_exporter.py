"""CSV para Excel/LibreOffice en español: ``;`` como separador, coma decimal y UTF-8 con
BOM (Excel detecta la codificación por el BOM).

Genera dos archivos junto a la ruta elegida: ``<nombre>_piezas.csv`` (despiece del
proyecto) y ``<nombre>_cortes.csv`` (lista de cortes y, tras una fila vacía, la
secuencia).
"""

from __future__ import annotations

import csv
from pathlib import Path

from exporters.base import ExportContext, register
from exporters.tables import cut_list_table, piece_list_table, sequence_table

DELIMITER = ";"
ENCODING = "utf-8-sig"
SEQUENCE_TITLE = "Secuencia de cortes"


def csv_paths(path: Path) -> tuple[Path, Path]:
    stem = path.with_suffix("")
    return (
        stem.with_name(f"{stem.name}_piezas.csv"),
        stem.with_name(f"{stem.name}_cortes.csv"),
    )


class CsvExporter:
    id = "csv"
    name = "CSV (piezas y cortes)…"
    file_filter = "CSV (*.csv)"
    suffix = ".csv"
    menu_order = 20

    def export(self, context: ExportContext, path: Path) -> list[Path]:
        pieces_path, cuts_path = csv_paths(Path(path))
        with pieces_path.open("w", encoding=ENCODING, newline="") as f:
            writer = csv.writer(f, delimiter=DELIMITER)
            headers, rows = piece_list_table(context)
            writer.writerow(headers)
            writer.writerows(rows)
        with cuts_path.open("w", encoding=ENCODING, newline="") as f:
            writer = csv.writer(f, delimiter=DELIMITER)
            headers, rows = cut_list_table(context)
            writer.writerow(headers)
            writer.writerows(rows)
            writer.writerow([])
            writer.writerow([SEQUENCE_TITLE])
            headers, rows = sequence_table(context)
            writer.writerow(headers)
            writer.writerows(rows)
        return [pieces_path, cuts_path]


register(CsvExporter())
