"""Generadores de despiece: Mueble (dimensiones + reglas) → lista de piezas.

En v1 solo se usa ``ManualGenerator`` (las piezas las carga el usuario). La interfaz
permite añadir más adelante generadores por reglas (escritorio, mesita, placard...)
sin tocar el optimizador. ``DeskGenerator`` es un ejemplo mínimo y **experimental**
de ese camino; no está registrado ni se muestra en la UI. Ver docs/08-roadmap-futuro.md.
"""

from __future__ import annotations

from typing import Protocol

from models.pieza import GrainDirection, PieceCategory, PieceSpec
from models.proyecto import Furniture
from utils.units import mm_to_internal


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


class DeskGenerator:
    """EXPERIMENTAL — escritorio simple a partir de sus medidas generales.

    Demuestra el pipeline Dimensiones → Despiece → Piezas → Optimizador::

        desk = Furniture("Escritorio", dimensions=FurnitureDimensions(12000, 7500, 6000),
                         generator_id=DeskGenerator.id)
        pieces = DeskGenerator().generate(desk, thickness=180)
        # → Tapa 1200 × 600, 2 Laterales 600 × 732, Faldón 1164 × 300

    Reglas (``t`` = espesor de la placa):

    * **Tapa**: ancho × profundidad, apoyada sobre los laterales (veta a lo ancho).
    * **Laterales** (2): profundidad × (alto − t), bajo la tapa (veta vertical).
    * **Faldón**: (ancho − 2t) × ``modesty_height_mm`` (300 por defecto), entre laterales.

    No se registra en ``GENERATORS``: para probarlo, ``register_generator(DeskGenerator())``.
    """

    id = "desk"
    name = "Escritorio (experimental)"
    DEFAULT_MODESTY_HEIGHT_MM = 300

    def generate(self, furniture: Furniture, thickness: int) -> list[PieceSpec]:
        dims = furniture.dimensions
        if dims is None:
            raise ValueError("El escritorio necesita las medidas generales del mueble")
        modesty = mm_to_internal(
            furniture.generator_params.get("modesty_height_mm", self.DEFAULT_MODESTY_HEIGHT_MM)
        )
        if min(dims.width, dims.height, dims.depth) <= 2 * thickness or modesty <= 0:
            raise ValueError("Medidas del escritorio demasiado chicas para el espesor de placa")
        return [
            PieceSpec(
                "Tapa",
                1,
                dims.width,
                dims.depth,
                thickness,
                category=PieceCategory.TAPA,
                grain=GrainDirection.HORIZONTAL,
            ),
            PieceSpec(
                "Lateral",
                2,
                dims.depth,
                dims.height - thickness,
                thickness,
                category=PieceCategory.LATERAL,
                grain=GrainDirection.VERTICAL,
            ),
            PieceSpec(
                "Faldón",
                1,
                dims.width - 2 * thickness,
                modesty,
                thickness,
                category=PieceCategory.FONDO,
                grain=GrainDirection.HORIZONTAL,
            ),
        ]


GENERATORS: dict[str, FurnitureGenerator] = {ManualGenerator.id: ManualGenerator()}
"""Generadores disponibles. ``DeskGenerator`` queda fuera a propósito (experimental)."""


def register_generator(generator: FurnitureGenerator) -> None:
    GENERATORS[generator.id] = generator


def get_generator(generator_id: str) -> FurnitureGenerator:
    try:
        return GENERATORS[generator_id]
    except KeyError:
        raise KeyError(f"Generador de muebles desconocido: {generator_id}") from None
