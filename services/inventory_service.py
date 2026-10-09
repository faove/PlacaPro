"""Inventario de placas enteras y stock de retazos."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from database.database import Database
from database.repositories import (
    OffcutRepository,
    ResultRepository,
    StockRepository,
    utc_now,
)
from models.placa import StockPlate
from models.resultado import OptimizationResult
from models.retazo import Offcut, OffcutStatus
from utils.units import format_length


class ConfirmationError(ValueError):
    """El plan no se puede confirmar (ya confirmado, sin stock, retazo no disponible…)."""


class InventoryService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.stock = StockRepository(db)
        self.offcuts = OffcutRepository(db)
        self.results = ResultRepository(db)

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

    def save_offcuts(self, result_id: int, labels: Iterable[str] | None = None) -> list[Offcut]:
        """Pasa a stock los retazos reutilizables de un resultado (todos si ``labels`` es
        ``None``). Los ya guardados se omiten; en el resultado quedan como ``IN_STOCK``
        con el id del stock, para no guardarlos dos veces.
        """
        result = self.results.get(result_id)
        by_label = {o.label: o for s in result.sheets for o in s.offcuts if o.label}
        wanted = set(by_label) if labels is None else set(labels)
        storable = (OffcutStatus.REUSABLE, OffcutStatus.IN_STOCK)
        for label in sorted(wanted):
            offcut = by_label.get(label)
            if offcut is None or offcut.status not in storable:
                raise ValueError(f"{label} no es un retazo reutilizable del resultado {result_id}")

        stored: list[Offcut] = []
        sheets = []
        with self.db.transaction():
            for sheet in result.sheets:
                offcuts = []
                for o in sheet.offcuts:
                    if o.label in wanted and o.status is OffcutStatus.REUSABLE:
                        place = (
                            f"placa {sheet.index + 1}, x = {format_length(o.x or 0)}, "
                            f"y = {format_length(o.y or 0)}"
                        )
                        saved = self.store_offcut(
                            replace(
                                o,
                                source_result_id=result_id,
                                notes=f"Retazo {o.label} del resultado {result_id} ({place})",
                            )
                        )
                        stored.append(saved)
                        o = replace(o, status=OffcutStatus.IN_STOCK, id=saved.id)
                    offcuts.append(o)
                sheets.append(replace(sheet, offcuts=tuple(offcuts)))
            self.results.update(replace(result, sheets=tuple(sheets)))
        return stored

    def mark_offcut_consumed(self, offcut_id: int) -> None:
        self.offcuts.set_status(offcut_id, OffcutStatus.CONSUMED)

    def delete_offcut(self, offcut_id: int) -> None:
        self.offcuts.delete(offcut_id)

    # -- confirmación de un plan
    def confirm_result(self, result_id: int) -> OptimizationResult:
        """Confirma un plan de corte: descuenta las placas de inventario usadas y marca
        como consumidos los retazos del stock usados. Todo o nada (una transacción).

        Lanza ``ConfirmationError`` si ya estaba confirmado, si no alcanza el stock o si un
        retazo ya no está disponible.
        """
        result = self.results.get(result_id)
        if result.is_confirmed:
            raise ConfirmationError("Este plan de corte ya fue confirmado")
        with self.db.transaction():
            for plate_format_id, quantity in result.stock_plates_used().items():
                available = self.stock.get_quantity(plate_format_id)
                if quantity > available:
                    raise ConfirmationError(
                        f"El plan usa {quantity} placas del inventario y solo quedan "
                        f"{available}. Vuelva a optimizar."
                    )
                self.stock.set_quantity(plate_format_id, available - quantity)
            for offcut_id in result.stock_offcuts_used():
                try:
                    offcut = self.offcuts.get(offcut_id)
                except LookupError:
                    offcut = None
                if offcut is None or offcut.status is not OffcutStatus.IN_STOCK:
                    raise ConfirmationError(
                        f"El retazo {offcut_id} del stock ya no está disponible. "
                        "Vuelva a optimizar."
                    )
                self.offcuts.set_status(offcut_id, OffcutStatus.CONSUMED)
            confirmed = replace(result, confirmed_at=utc_now())
            self.results.update(confirmed)
        return confirmed
