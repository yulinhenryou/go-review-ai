"""Applies the Alembic migrations in `migrations/` to a database.

    uv run python -m weiqi.storage.migrate upgrade sqlite:///path/to/weiqi.db

Migrations run on a connection we open, inside one transaction, so a failed
migration leaves the schema as it was (on PostgreSQL; SQLite commits some
DDL implicitly).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine

from weiqi.storage.database import connect

MIGRATIONS: Final = Path(__file__).with_name("migrations")


def _config(connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.attributes["connection"] = connection
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Migrates the schema up to `revision` (default: the latest)."""
    with engine.begin() as connection:
        command.upgrade(_config(connection), revision)


def downgrade(engine: Engine, revision: str = "base") -> None:
    """Migrates the schema down to `revision` (default: no tables)."""
    with engine.begin() as connection:
        command.downgrade(_config(connection), revision)


def current_revision(engine: Engine) -> str | None:
    """The revision the database is at, or `None` before the first migration."""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply database migrations.")
    parser.add_argument("action", choices=["upgrade", "downgrade", "current"])
    parser.add_argument("url", help="SQLAlchemy URL, e.g. sqlite:///weiqi.db")
    parser.add_argument("--revision", help="default: head for upgrade, base for downgrade")
    args = parser.parse_args(argv)
    engine = connect(args.url)
    try:
        if args.action == "upgrade":
            upgrade(engine, args.revision or "head")
        elif args.action == "downgrade":
            downgrade(engine, args.revision or "base")
        print(current_revision(engine) or "base")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
