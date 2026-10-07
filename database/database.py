"""Conexión SQLite, transacciones anidables y migraciones."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from database.models import MIGRATIONS, SCHEMA_VERSION
from utils.constants import default_db_path


class Database:
    """Envoltorio de una conexión SQLite.

    * ``foreign_keys`` activadas.
    * Modo autocommit de sqlite3 (``isolation_level=None``) con transacciones explícitas
      mediante :meth:`transaction`, que admite anidamiento con SAVEPOINT.
    * ``path=":memory:"`` para tests.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._depth = 0

    @classmethod
    def open_default(cls) -> Database:
        db = cls(default_db_path())
        db.migrate()
        return db

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Transacción atómica; las anidadas usan SAVEPOINT y revierten solo su parte."""
        savepoint = f"sp_{self._depth}"
        if self._depth == 0:
            self._conn.execute("BEGIN")
        else:
            self._conn.execute(f"SAVEPOINT {savepoint}")
        self._depth += 1
        try:
            yield self._conn
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("ROLLBACK")
            else:
                self._conn.execute(f"ROLLBACK TO {savepoint}")
                self._conn.execute(f"RELEASE {savepoint}")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("COMMIT")
            else:
                self._conn.execute(f"RELEASE {savepoint}")

    @property
    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def migrate(self) -> int:
        """Aplica las migraciones pendientes. Idempotente. Devuelve la versión final."""
        current = self.schema_version
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"La base de datos es de una versión más nueva ({current}) que la aplicación "
                f"({SCHEMA_VERSION})"
            )
        for version in range(current, SCHEMA_VERSION):
            with self.transaction():
                for statement in _split_statements(MIGRATIONS[version]):
                    self._conn.execute(statement)
                self._conn.execute(f"PRAGMA user_version = {version + 1}")
        return self.schema_version

    def close(self) -> None:
        self._conn.close()


def _split_statements(script: str) -> list[str]:
    """Separa un script DDL en sentencias (``executescript`` haría COMMIT implícito)."""
    lines = [line for line in script.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
