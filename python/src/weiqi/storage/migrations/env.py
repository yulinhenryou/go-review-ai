"""Alembic environment: runs migrations on the connection `weiqi.storage.migrate` passes in."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection

from weiqi.storage.schema import metadata


def run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        # SQLite cannot alter most constraints in place; batch mode copies the table.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline (SQL script) migrations are not supported")
connection = context.config.attributes.get("connection")
if not isinstance(connection, Connection):
    raise RuntimeError("run migrations through weiqi.storage.migrate")
run(connection)
