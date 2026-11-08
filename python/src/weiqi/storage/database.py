"""Opening a database: SQLite for development and tests, PostgreSQL in CI and later."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event, make_url


def _enable_sqlite_foreign_keys(connection: Any, _record: object) -> None:
    # SQLite ignores foreign keys unless each connection turns them on.
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def connect(url: str) -> Engine:
    """An SQLAlchemy engine for `url` (only SQLite and PostgreSQL are supported)."""
    backend = make_url(url).get_backend_name()
    if backend not in {"sqlite", "postgresql"}:
        raise ValueError("only SQLite and PostgreSQL databases are supported")
    engine = create_engine(url)
    if backend == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine
