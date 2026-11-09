"""The SQL schema, as SQLAlchemy Core tables (ARCHITECTURE §10.3, ADR-015, ADR-P08).

Written for both SQLite and PostgreSQL: plain types only, hashes and ids as
fixed-length hex text, timestamps in UTC, JSON in `TEXT`, ownership as a
compressed binary column. Alembic migrations in `migrations/` create the
same tables; a test compares the two so they cannot drift apart.

Tables (M3, the analysis cache):

- `engine_identity`: an engine as it reported itself, one row per identity.
- `engine_query`: one analysis query sent to that engine, with its timing.
- `position_eval`: one analysed turn, keyed by `query_key` (ADR-P03), with
  the position's `stones_hash` as an index for finding it across games.

M4 adds `position_eval.allow_move`: the move a restricted search was limited
to (GTP vertex or "pass"), `NULL` for a free search.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import (
    Column,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
)

ENCODING_VERSION: Final = 1
"""How `position_eval.candidates` and `ownership` are encoded (see `results.py`)."""

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def _created_at() -> Column[object]:
    return Column("created_at", DateTime(timezone=True), nullable=False)


engine_identity = Table(
    "engine_identity",
    metadata,
    Column("identity_key", String(64), primary_key=True),
    Column("version", String(80), nullable=False),
    Column("model_name", String(200), nullable=False),
    Column("model_sha256", String(64), nullable=False),
    Column("config_sha256", String(64), nullable=False),
    Column("overrides", Text, nullable=False),
    _created_at(),
)

engine_query = Table(
    "engine_query",
    metadata,
    Column("query_id", String(32), primary_key=True),
    Column(
        "identity_key",
        String(64),
        ForeignKey("engine_identity.identity_key"),
        nullable=False,
        index=True,
    ),
    Column("turn_count", Integer, nullable=False),
    Column("elapsed_seconds", Double, nullable=False),
    _created_at(),
)

position_eval = Table(
    "position_eval",
    metadata,
    Column("query_key", String(64), primary_key=True),
    Column("query_id", String(32), ForeignKey("engine_query.query_id"), nullable=False, index=True),
    Column("turn", Integer, nullable=False),
    Column("stones_hash", String(32), nullable=False, index=True),
    Column("situation_hash", String(32), nullable=False),
    Column("current_player", String(1), nullable=False),
    Column("max_visits", Integer, nullable=False),
    Column("root_visits", Integer),
    Column("winrate_black", Double),
    Column("score_lead_black", Double),
    Column("candidates", Text, nullable=False),
    Column("ownership", LargeBinary),
    Column("engine_warnings", Text, nullable=False),
    Column("encoding", Integer, nullable=False),
    _created_at(),
    Column("allow_move", String(8)),
)
