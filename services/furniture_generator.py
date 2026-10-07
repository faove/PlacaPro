"""Generadores de despiece: Mueble (dimensiones + reglas) → lista de piezas.

En v1 solo existe ``ManualGenerator`` (las piezas las carga el usuario). La interfaz
permite añadir más adelante generadores por reglas (escritorio, mesita, placard...)
sin tocar el optimizador. Ver docs/08-roadmap-futuro.md.
"""

from __future__ import annotations

from typing import Protocol

from models.pieza import PieceSpec
from models.proyecto import Furniture


class FurnitureGenerator(Protocol):
    id: str
    name: str

    def generate(self, furniture: Furniture, thickness: int) -> list[PieceSpec]:
        """Devuelve el despiece del mueble. ``thickness`` es el espesor de la placa (dmm)."""
        ...


class ManualGenerator:
    """Despiece cargado a mano: devuelve las piezas tal cual."""

    id = "manual"
    name = "Manual"

    def generate(self, furniture: Furniture, thickness: int) -> list[PieceSpec]:
        return list(furniture.pieces)


GENERATORS: dict[str, FurnitureGenerator] = {ManualGenerator.id: ManualGenerator()}


def register_generator(generator: FurnitureGenerator) -> None:
    GENERATORS[generator.id] = generator


def get_generator(generator_id: str) -> FurnitureGenerator:
    try:
        return GENERATORS[generator_id]
    except KeyError:
        raise KeyError(f"Generador de muebles desconocido: {generator_id}") from None
