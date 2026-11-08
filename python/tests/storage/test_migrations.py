"""Migrations create exactly the schema module's tables, on SQLite and
PostgreSQL (ROADMAP M3 acceptance 6), and can be undone and redone."""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

from weiqi.storage.database import connect
from weiqi.storage.migrate import MIGRATIONS, current_revision, downgrade, upgrade
from weiqi.storage.schema import metadata

TABLES = {"engine_identity", "engine_query", "position_eval"}


def differences(engine: Engine) -> list[object]:
    with engine.connect() as connection:
        return list(compare_metadata(MigrationContext.configure(connection), metadata))


def test_the_migrations_build_the_schema_module_exactly(database: Engine) -> None:
    assert current_revision(database) is None
    upgrade(database)
    assert current_revision(database) == "0001"
    assert set(inspect(database).get_table_names()) >= TABLES
    assert differences(database) == []


def test_migrations_can_be_undone_and_redone(database: Engine) -> None:
    upgrade(database)
    downgrade(database)
    assert current_revision(database) is None
    assert not TABLES & set(inspect(database).get_table_names())
    upgrade(database)
    assert differences(database) == []


def test_there_is_one_line_of_migrations() -> None:
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    assert ScriptDirectory.from_config(config).get_heads() == ["0001"]


def test_only_sqlite_and_postgresql_are_accepted() -> None:
    with pytest.raises(ValueError, match="SQLite and PostgreSQL"):
        connect("mysql+pymysql://user@localhost/db")
