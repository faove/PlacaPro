"""Inventario de placas enteras y stock de retazos."""

from __future__ import annotations

from dataclasses import replace

from database.database import Database
from database.repositories import OffcutRepository, StockRepository
from models.placa import StockPlate
from models.retazo import Offcut, OffcutStatus


class InventoryService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.stock = StockRepository(db)
        self.offcuts = OffcutRepository(db)

    # -- placas enteras
    def list_stock(self) -> list[StockPlate]:
        return self.stock.list()

    def available_plates(self, plate_format_id: int) -> int:
        return self.stock.get_quantity(plate_format_id)

    def set_available_plates(self, plate_format_id: int, quantity: int) -> None:
        self.stock.set_quantity(plate_format_id, quantity)

    def add_plates(self, plate_format_id: int, quantity: int) -> int:
        return self.stock.add(plate_format_id, quantity)

    def consume_plates(self, plate_format_id: int, quantity: int) -> int:
        """Descuenta placas; lanza ``InsufficientStockError`` si no alcanzan."""
        return self.stock.consume(plate_format_id, quantity)

    # -- retazos
    def available_offcuts(
        self, material_id: int | None = None, thickness: int | None = None
    ) -> list[Offcut]:
        return self.offcuts.list(OffcutStatus.IN_STOCK, material_id, thickness)

    def store_offcut(self, offcut: Offcut) -> Offcut:
        """Guarda un retazo en el stock (estado ``IN_STOCK``, posición en placa descartada)."""
        return self.offcuts.save(
            replace(offcut, id=None, status=OffcutStatus.IN_STOCK, x=None, y=None, sheet_index=None)
        )

    def mark_offcut_consumed(self, offcut_id: int) -> None:
        self.offcuts.set_status(offcut_id, OffcutStatus.CONSUMED)

    def delete_offcut(self, offcut_id: int) -> None:
        self.offcuts.delete(offcut_id)
