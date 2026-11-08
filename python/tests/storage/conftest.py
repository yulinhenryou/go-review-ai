"""Every storage test runs on SQLite, and on PostgreSQL when
`TEST_POSTGRESQL_URL` names a database the tests may empty (CI starts one)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from weiqi.storage.database import connect
from weiqi.storage.migrate import downgrade

POSTGRESQL_URL = os.environ.get("TEST_POSTGRESQL_URL")


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                not POSTGRESQL_URL, reason="set TEST_POSTGRESQL_URL to test PostgreSQL"
            ),
        ),
    ]
)
def database(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Engine]:
    """An empty database, migrated by each test as it needs."""
    url = f"sqlite:///{tmp_path / 'test.db'}" if request.param == "sqlite" else POSTGRESQL_URL
    assert url is not None
    engine = connect(url)
    try:
        yield engine
    finally:
        downgrade(engine)  # PostgreSQL outlives the test; leave it empty
        engine.dispose()
