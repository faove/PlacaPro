"""Casos de uso de placas, materiales y proveedores."""

from __future__ import annotations

from database.database import Database
from database.repositories import (
    MaterialRepository,
    PlateFormatRepository,
    StockRepository,
    SupplierRepository,
)
from models.placa import Material, PlateFormat, Supplier
from models.validation import ValidationFailed, ValidationReport, validate_plate


class PlateService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.plates = PlateFormatRepository(db)
        self.materials = MaterialRepository(db)
        self.suppliers = SupplierRepository(db)
        self.stock = StockRepository(db)

    def list_formats(self) -> list[PlateFormat]:
        return self.plates.list()

    def get_format(self, plate_id: int) -> PlateFormat:
        return self.plates.get(plate_id)

    def save_format(self, plate: PlateFormat) -> PlateFormat:
        """Valida y guarda ("Guardar placa"). Lanza ``ValidationFailed`` si hay errores."""
        report = ValidationReport(validate_plate(plate))
        if report.has_errors:
            raise ValidationFailed(report)
        return self.plates.save(plate)

    def delete_format(self, plate_id: int) -> None:
        """Elimina el formato; los proyectos que lo usaban quedan sin placa seleccionada."""
        self.plates.delete(plate_id)

    def list_materials(self) -> list[Material]:
        return self.materials.list()

    def save_material(self, material: Material) -> Material:
        return self.materials.save(material)

    def list_suppliers(self) -> list[Supplier]:
        return self.suppliers.list()

    def save_supplier(self, supplier: Supplier) -> Supplier:
        return self.suppliers.save(supplier)
