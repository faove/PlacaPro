"""Entidades de costos (preparadas para una versión futura; sin UI en v1).

Los importes se guardan en centavos enteros para evitar errores de redondeo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class MaterialCost:
    plate_format_id: int
    plate_price_cents: int
    price_per_m2_cents: int


@dataclass(frozen=True)
class HardwareItem:
    """Herraje (bisagra, corredera, tirador...)."""

    name: str
    unit_price_cents: int
    id: int | None = None


@dataclass(frozen=True)
class HardwareLine:
    item: HardwareItem
    quantity: int

    @property
    def total_cents(self) -> int:
        return self.item.unit_price_cents * self.quantity


@dataclass(frozen=True)
class LaborCost:
    hours: Decimal
    hourly_rate_cents: int

    @property
    def total_cents(self) -> int:
        return int((self.hours * self.hourly_rate_cents).to_integral_value())


@dataclass(frozen=True)
class CostBreakdown:
    plates_cents: int = 0
    waste_cents: int = 0
    hardware_cents: int = 0
    labor_cents: int = 0
    sale_price_cents: int = 0
    hardware_lines: tuple[HardwareLine, ...] = field(default_factory=tuple)

    @property
    def total_cents(self) -> int:
        return self.plates_cents + self.hardware_cents + self.labor_cents

    @property
    def margin_pct(self) -> Decimal:
        if not self.sale_price_cents:
            return Decimal(0)
        return (Decimal(self.sale_price_cents - self.total_cents) * 100) / self.sale_price_cents
