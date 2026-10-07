"""Utilidades internas compartidas por las entidades de dominio."""

from __future__ import annotations

from datetime import datetime


def require_int(name: str, value: object) -> None:
    """Exige un ``int`` real (no ``bool`` ni ``float``) para medidas en unidades internas."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} debe ser int (décimas de mm), no {type(value).__name__}")


def dt_to_str(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def dt_from_str(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
