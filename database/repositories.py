"""Repositorios: traducen entre filas SQLite y entidades de dominio."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from database.database import Database
from models._base import dt_from_str
from models.parametros import CuttingParameters
from models.pieza import GrainDirection, PieceCategory, PieceSpec
from models.placa import Material, MaterialKind, PlateFormat, PlateGrain, StockPlate, Supplier
from models.proyecto import Furniture, FurnitureDimensions, Project
from models.resultado import OptimizationResult
from models.retazo import Offcut, OffcutStatus


class NotFoundError(LookupError):
    """La entidad pedida no existe."""


class InsufficientStockError(ValueError):
    """Se intentó consumir más placas de las disponibles."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def _require(row: sqlite3.Row | None, what: str, entity_id: int) -> sqlite3.Row:
    if row is None:
        raise NotFoundError(f"{what} {entity_id} no existe")
    return row


# --------------------------------------------------------------------------- materiales


class MaterialRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Material:
        return Material(row["name"], MaterialKind(row["kind"]), row["notes"], row["id"])

    def list(self) -> list[Material]:
        return [self._from_row(r) for r in self.db.query("SELECT * FROM materials ORDER BY name")]

    def get(self, material_id: int) -> Material:
        row = self.db.query_one("SELECT * FROM materials WHERE id = ?", (material_id,))
        return self._from_row(_require(row, "Material", material_id))

    def get_by_name(self, name: str) -> Material | None:
        row = self.db.query_one("SELECT * FROM materials WHERE name = ?", (name,))
        return self._from_row(row) if row else None

    def save(self, material: Material) -> Material:
        values = (material.name, material.kind.value, material.notes)
        if material.id is None:
            cur = self.db.execute(
                "INSERT INTO materials (name, kind, notes) VALUES (?, ?, ?)", values
            )
            return replace(material, id=cur.lastrowid)
        cur = self.db.execute(
            "UPDATE materials SET name = ?, kind = ?, notes = ? WHERE id = ?",
            (*values, material.id),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"Material {material.id} no existe")
        return material

    def delete(self, material_id: int) -> None:
        self.db.execute("DELETE FROM materials WHERE id = ?", (material_id,))


class SupplierRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Supplier:
        return Supplier(row["name"], row["contact"], row["id"])

    def list(self) -> list[Supplier]:
        return [self._from_row(r) for r in self.db.query("SELECT * FROM suppliers ORDER BY name")]

    def get(self, supplier_id: int) -> Supplier:
        row = self.db.query_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
        return self._from_row(_require(row, "Proveedor", supplier_id))

    def save(self, supplier: Supplier) -> Supplier:
        if supplier.id is None:
            cur = self.db.execute(
                "INSERT INTO suppliers (name, contact) VALUES (?, ?)",
                (supplier.name, supplier.contact),
            )
            return replace(supplier, id=cur.lastrowid)
        cur = self.db.execute(
            "UPDATE suppliers SET name = ?, contact = ? WHERE id = ?",
            (supplier.name, supplier.contact, supplier.id),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"Proveedor {supplier.id} no existe")
        return supplier

    def delete(self, supplier_id: int) -> None:
        self.db.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))


# --------------------------------------------------------------------------- placas


class PlateFormatRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _from_row(row: sqlite3.Row) -> PlateFormat:
        return PlateFormat(
            name=row["name"],
            width=row["width_dmm"],
            height=row["height_dmm"],
            thickness=row["thickness_dmm"],
            material_id=row["material_id"],
            color=row["color"],
            supplier_id=row["supplier_id"],
            grain=PlateGrain(row["grain"]),
            price_cents=row["price_cents"],
            id=row["id"],
        )

    def list(self) -> list[PlateFormat]:
        rows = self.db.query("SELECT * FROM plate_formats ORDER BY name, id")
        return [self._from_row(r) for r in rows]

    def get(self, plate_id: int) -> PlateFormat:
        row = self.db.query_one("SELECT * FROM plate_formats WHERE id = ?", (plate_id,))
        return self._from_row(_require(row, "Placa", plate_id))

    def save(self, plate: PlateFormat) -> PlateFormat:
        values = (
            plate.name,
            plate.width,
            plate.height,
            plate.thickness,
            plate.material_id,
            plate.color,
            plate.supplier_id,
            plate.grain.value,
            plate.price_cents,
        )
        if plate.id is None:
            cur = self.db.execute(
                """INSERT INTO plate_formats (name, width_dmm, height_dmm, thickness_dmm,
                   material_id, color, supplier_id, grain, price_cents, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*values, utc_now().isoformat()),
            )
            return replace(plate, id=cur.lastrowid)
        cur = self.db.execute(
            """UPDATE plate_formats SET name = ?, width_dmm = ?, height_dmm = ?,
               thickness_dmm = ?, material_id = ?, color = ?, supplier_id = ?, grain = ?,
               price_cents = ? WHERE id = ?""",
            (*values, plate.id),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"Placa {plate.id} no existe")
        return plate

    def delete(self, plate_id: int) -> None:
        self.db.execute("DELETE FROM plate_formats WHERE id = ?", (plate_id,))


class StockRepository:
    """Inventario de placas enteras por formato."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self) -> list[StockPlate]:
        rows = self.db.query(
            "SELECT * FROM stock_plates WHERE quantity > 0 ORDER BY plate_format_id"
        )
        return [StockPlate(r["plate_format_id"], r["quantity"]) for r in rows]

    def get_quantity(self, plate_format_id: int) -> int:
        row = self.db.query_one(
            "SELECT quantity FROM stock_plates WHERE plate_format_id = ?", (plate_format_id,)
        )
        return row["quantity"] if row else 0

    def set_quantity(self, plate_format_id: int, quantity: int) -> None:
        if quantity < 0:
            raise ValueError("La cantidad en stock no puede ser negativa")
        self.db.execute(
            """INSERT INTO stock_plates (plate_format_id, quantity) VALUES (?, ?)
               ON CONFLICT(plate_format_id) DO UPDATE SET quantity = excluded.quantity""",
            (plate_format_id, quantity),
        )

    def add(self, plate_format_id: int, quantity: int) -> int:
        with self.db.transaction():
            new_quantity = self.get_quantity(plate_format_id) + quantity
            self.set_quantity(plate_format_id, new_quantity)
        return new_quantity

    def consume(self, plate_format_id: int, quantity: int) -> int:
        with self.db.transaction():
            available = self.get_quantity(plate_format_id)
            if quantity > available:
                raise InsufficientStockError(
                    f"Se necesitan {quantity} placas y solo hay {available} en stock"
                )
            self.set_quantity(plate_format_id, available - quantity)
        return available - quantity


# --------------------------------------------------------------------------- proyectos


@dataclass(frozen=True)
class ProjectSummary:
    id: int
    name: str
    description: str
    updated_at: datetime
    piece_count: int


class ProjectRepository:
    """Guarda y carga el agregado completo Proyecto → Muebles → Piezas."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self) -> list[ProjectSummary]:
        rows = self.db.query(
            """SELECT p.id, p.name, p.description, p.updated_at,
                      COALESCE(SUM(pc.quantity), 0) AS piece_count
               FROM projects p
               LEFT JOIN furniture f ON f.project_id = p.id
               LEFT JOIN pieces pc ON pc.furniture_id = f.id
               GROUP BY p.id ORDER BY p.updated_at DESC, p.id DESC"""
        )
        return [
            ProjectSummary(
                r["id"],
                r["name"],
                r["description"],
                datetime.fromisoformat(r["updated_at"]),
                r["piece_count"],
            )
            for r in rows
        ]

    def exists(self, project_id: int) -> bool:
        return self.db.query_one("SELECT 1 FROM projects WHERE id = ?", (project_id,)) is not None

    def find_by_name(self, name: str) -> list[int]:
        return [r["id"] for r in self.db.query("SELECT id FROM projects WHERE name = ?", (name,))]

    def get(self, project_id: int) -> Project:
        row = _require(
            self.db.query_one("SELECT * FROM projects WHERE id = ?", (project_id,)),
            "Proyecto",
            project_id,
        )
        furniture: list[Furniture] = []
        for f in self.db.query(
            "SELECT * FROM furniture WHERE project_id = ? ORDER BY sort_order, id", (project_id,)
        ):
            dims = None
            if f["width_dmm"] is not None:
                dims = FurnitureDimensions(f["width_dmm"], f["height_dmm"], f["depth_dmm"])
            pieces = [
                self._piece_from_row(p)
                for p in self.db.query(
                    "SELECT * FROM pieces WHERE furniture_id = ? ORDER BY sort_order, id",
                    (f["id"],),
                )
            ]
            furniture.append(
                Furniture(
                    name=f["name"],
                    pieces=pieces,
                    dimensions=dims,
                    generator_id=f["generator_id"],
                    generator_params=json.loads(f["generator_params_json"]),
                    id=f["id"],
                )
            )
        return Project(
            name=row["name"],
            description=row["description"],
            plate_format_id=row["plate_format_id"],
            params=CuttingParameters.from_dict(json.loads(row["params_json"])),
            furniture=furniture,
            created_at=dt_from_str(row["created_at"]),
            updated_at=dt_from_str(row["updated_at"]),
            id=row["id"],
        )

    @staticmethod
    def _piece_from_row(row: sqlite3.Row) -> PieceSpec:
        return PieceSpec(
            name=row["name"],
            quantity=row["quantity"],
            width=row["width_dmm"],
            height=row["height_dmm"],
            thickness=row["thickness_dmm"],
            category=PieceCategory(row["category"]),
            material_id=row["material_id"],
            can_rotate=bool(row["can_rotate"]),
            grain=GrainDirection(row["grain"]),
            fixed_orientation=bool(row["fixed_orientation"]),
            notes=row["notes"],
            id=row["id"],
        )

    def save(self, project: Project) -> Project:
        """Inserta o actualiza el proyecto completo en una transacción.

        Actualiza en el propio objeto ``id``, fechas e ids de muebles y piezas, y lo devuelve.
        Los muebles y piezas se reescriben (sus ids pueden cambiar).
        """
        now = utc_now()
        params_json = json.dumps(project.params.to_dict(), sort_keys=True)
        with self.db.transaction():
            if project.id is None:
                created = project.created_at or now
                cur = self.db.execute(
                    """INSERT INTO projects (name, description, plate_format_id, params_json,
                       created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        project.name,
                        project.description,
                        project.plate_format_id,
                        params_json,
                        created.isoformat(),
                        now.isoformat(),
                    ),
                )
                project.id = cur.lastrowid
                project.created_at = created
            else:
                cur = self.db.execute(
                    """UPDATE projects SET name = ?, description = ?, plate_format_id = ?,
                       params_json = ?, updated_at = ? WHERE id = ?""",
                    (
                        project.name,
                        project.description,
                        project.plate_format_id,
                        params_json,
                        now.isoformat(),
                        project.id,
                    ),
                )
                if cur.rowcount == 0:
                    raise NotFoundError(f"Proyecto {project.id} no existe")
                self.db.execute("DELETE FROM furniture WHERE project_id = ?", (project.id,))
            project.updated_at = now
            for f_order, item in enumerate(project.furniture):
                self._insert_furniture(project.id, item, f_order)
        return project

    def _insert_furniture(self, project_id: int, item: Furniture, order: int) -> None:
        dims = item.dimensions
        cur = self.db.execute(
            """INSERT INTO furniture (project_id, name, width_dmm, height_dmm, depth_dmm,
               generator_id, generator_params_json, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                item.name,
                dims.width if dims else None,
                dims.height if dims else None,
                dims.depth if dims else None,
                item.generator_id,
                json.dumps(item.generator_params, sort_keys=True),
                order,
            ),
        )
        item.id = cur.lastrowid
        saved: list[PieceSpec] = []
        for p_order, piece in enumerate(item.pieces):
            cur = self.db.execute(
                """INSERT INTO pieces (furniture_id, name, category, quantity, width_dmm,
                   height_dmm, thickness_dmm, material_id, can_rotate, grain, fixed_orientation,
                   sort_order, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.id,
                    piece.name,
                    piece.category.value,
                    piece.quantity,
                    piece.width,
                    piece.height,
                    piece.thickness,
                    piece.material_id,
                    int(piece.can_rotate),
                    piece.grain.value,
                    int(piece.fixed_orientation),
                    p_order,
                    piece.notes,
                ),
            )
            saved.append(replace(piece, id=cur.lastrowid))
        item.pieces = saved

    def duplicate(self, project_id: int, new_name: str) -> Project:
        return self.save(self.get(project_id).duplicate(new_name))

    def delete(self, project_id: int) -> None:
        cur = self.db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if cur.rowcount == 0:
            raise NotFoundError(f"Proyecto {project_id} no existe")


# --------------------------------------------------------------------------- resultados


@dataclass(frozen=True)
class ResultSummary:
    id: int
    project_id: int
    created_at: datetime
    strategy: str
    sheets_count: int
    utilization: float


class ResultRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, result: OptimizationResult) -> OptimizationResult:
        if result.project_id is None:
            raise ValueError("El resultado debe pertenecer a un proyecto guardado")
        created = result.created_at or utc_now()
        cur = self.db.execute(
            """INSERT INTO optimization_results (project_id, created_at, strategy, score_json,
               sheets_count, utilization, params_json, result_json, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.project_id,
                created.isoformat(),
                result.strategy,
                json.dumps(list(result.score)),
                result.sheets_count,
                result.utilization,
                json.dumps(result.params.to_dict(), sort_keys=True),
                json.dumps(replace(result, created_at=created).to_dict()),
                result.duration_ms,
            ),
        )
        return replace(result, id=cur.lastrowid, created_at=created)

    def update(self, result: OptimizationResult) -> None:
        """Reescribe el JSON de un resultado guardado (p. ej. retazos pasados a stock)."""
        if result.id is None:
            raise ValueError("El resultado no está guardado")
        cur = self.db.execute(
            "UPDATE optimization_results SET result_json = ? WHERE id = ?",
            (json.dumps(result.to_dict()), result.id),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"Resultado {result.id} no existe")

    def _from_row(self, row: sqlite3.Row) -> OptimizationResult:
        result = OptimizationResult.from_dict(json.loads(row["result_json"]))
        return replace(result, id=row["id"], project_id=row["project_id"])

    def get(self, result_id: int) -> OptimizationResult:
        row = self.db.query_one("SELECT * FROM optimization_results WHERE id = ?", (result_id,))
        return self._from_row(_require(row, "Resultado", result_id))

    def latest(self, project_id: int) -> OptimizationResult | None:
        row = self.db.query_one(
            """SELECT * FROM optimization_results WHERE project_id = ?
               ORDER BY created_at DESC, id DESC LIMIT 1""",
            (project_id,),
        )
        return self._from_row(row) if row else None

    def list(self, project_id: int) -> list[ResultSummary]:
        rows = self.db.query(
            """SELECT id, project_id, created_at, strategy, sheets_count, utilization
               FROM optimization_results WHERE project_id = ? ORDER BY created_at DESC, id DESC""",
            (project_id,),
        )
        return [
            ResultSummary(
                r["id"],
                r["project_id"],
                datetime.fromisoformat(r["created_at"]),
                r["strategy"],
                r["sheets_count"],
                r["utilization"],
            )
            for r in rows
        ]


# --------------------------------------------------------------------------- retazos


class OffcutRepository:
    """Stock de retazos reutilizables."""

    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Offcut:
        return Offcut(
            width=row["width_dmm"],
            height=row["height_dmm"],
            thickness=row["thickness_dmm"],
            status=OffcutStatus(row["status"]),
            plate_format_id=row["plate_format_id"],
            material_id=row["material_id"],
            source_result_id=row["source_result_id"],
            needs_trim=bool(row["needs_trim"]),
            created_at=dt_from_str(row["created_at"]),
            notes=row["notes"],
            id=row["id"],
        )

    def list(
        self,
        status: OffcutStatus | None = None,
        material_id: int | None = None,
        thickness: int | None = None,
    ) -> list[Offcut]:
        sql, args = "SELECT * FROM offcuts WHERE 1 = 1", []
        if status is not None:
            sql += " AND status = ?"
            args.append(status.value)
        if material_id is not None:
            sql += " AND material_id = ?"
            args.append(material_id)
        if thickness is not None:
            sql += " AND thickness_dmm = ?"
            args.append(thickness)
        sql += " ORDER BY width_dmm * height_dmm DESC, id"
        return [self._from_row(r) for r in self.db.query(sql, tuple(args))]

    def get(self, offcut_id: int) -> Offcut:
        row = self.db.query_one("SELECT * FROM offcuts WHERE id = ?", (offcut_id,))
        return self._from_row(_require(row, "Retazo", offcut_id))

    def save(self, offcut: Offcut) -> Offcut:
        created = offcut.created_at or utc_now()
        values = (
            offcut.plate_format_id,
            offcut.width,
            offcut.height,
            offcut.thickness,
            offcut.material_id,
            offcut.status.value,
            offcut.source_result_id,
            int(offcut.needs_trim),
            created.isoformat(),
            offcut.notes,
        )
        if offcut.id is None:
            cur = self.db.execute(
                """INSERT INTO offcuts (plate_format_id, width_dmm, height_dmm, thickness_dmm,
                   material_id, status, source_result_id, needs_trim, created_at, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            return replace(offcut, id=cur.lastrowid, created_at=created)
        cur = self.db.execute(
            """UPDATE offcuts SET plate_format_id = ?, width_dmm = ?, height_dmm = ?,
               thickness_dmm = ?, material_id = ?, status = ?, source_result_id = ?,
               needs_trim = ?, created_at = ?, notes = ? WHERE id = ?""",
            (*values, offcut.id),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"Retazo {offcut.id} no existe")
        return replace(offcut, created_at=created)

    def set_status(self, offcut_id: int, status: OffcutStatus) -> None:
        cur = self.db.execute(
            "UPDATE offcuts SET status = ? WHERE id = ?", (status.value, offcut_id)
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"Retazo {offcut_id} no existe")

    def delete(self, offcut_id: int) -> None:
        self.db.execute("DELETE FROM offcuts WHERE id = ?", (offcut_id,))


# --------------------------------------------------------------------------- metadatos


class MetaRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str) -> str | None:
        row = self.db.query_one("SELECT value FROM app_meta WHERE key = ?", (key,))
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            """INSERT INTO app_meta (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
