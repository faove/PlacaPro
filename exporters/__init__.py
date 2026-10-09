"""Exportadores de PlacaPro.

``load_exporters()`` importa los módulos de formato (que se registran en ``EXPORTERS``).
Se hace bajo demanda porque PDF y SVG usan Qt y los servicios no deben importarlo.
"""

from __future__ import annotations

import importlib

from exporters.base import (
    EXPORTERS,
    ExportContext,
    Exporter,
    exporters_in_menu_order,
    get_exporter,
    register,
)

FORMAT_MODULES = ("exporters.pdf_exporter", "exporters.csv_exporter", "exporters.svg_exporter")
"""Un formato nuevo = un módulo que llame a ``register(...)`` + una entrada aquí."""


def load_exporters() -> list[Exporter]:
    """Registra todos los formatos (idempotente) y los devuelve en el orden del menú."""
    for name in FORMAT_MODULES:
        importlib.import_module(name)
    return exporters_in_menu_order()


__all__ = [
    "EXPORTERS",
    "ExportContext",
    "Exporter",
    "exporters_in_menu_order",
    "get_exporter",
    "load_exporters",
    "register",
]
