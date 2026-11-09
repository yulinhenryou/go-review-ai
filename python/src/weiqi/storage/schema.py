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
to (GTP vertex or "pass"), `NULL` for a free search, and the reviews:

- `game`: one SGF file as uploaded, keyed by a text id, unique by its SHA-256.
- `review_run`: one review of a game: engine identity, confirmed rules and
  komi, the review settings, and the whole result as canonical JSON.
- `move_metric`: one row per run, move and score-loss definition, so
  profiles can aggregate losses in SQL without reading result documents.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import (
    Column,
    DateTime,
    Double,
    ForeignKey,
    Index,
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

game = Table(
    "game",
    metadata,
    Column("game_id", String(32), primary_key=True),
    Column("sgf_sha256", String(64), nullable=False, unique=True),
    Column("sgf", LargeBinary, nullable=False),
    _created_at(),
)

review_run = Table(
    "review_run",
    metadata,
    Column("run_id", String(32), primary_key=True),
    Column("game_id", String(32), ForeignKey("game.game_id"), nullable=False, index=True),
    Column("identity_key", String(64), ForeignKey("engine_identity.identity_key"), nullable=False),
    Column("rules", String(20), nullable=False),
    Column("komi", Double, nullable=False),
    Column("settings", Text, nullable=False),
    Column("schema_version", String(20), nullable=False),
    Column("status", String(10), nullable=False),
    Column("result", Text, nullable=False),
    _created_at(),
)

move_metric = Table(
    "move_metric",
    metadata,
    Column("run_id", String(32), ForeignKey("review_run.run_id"), primary_key=True),
    Column("move_number", Integer, primary_key=True),
    Column("definition", String(40), primary_key=True),
    Column("color", String(1), nullable=False),
    Column("raw_score_loss", Double),
    Column("score_loss", Double),
    Column("winrate_delta_pp", Double),
    Column("severity", String(10)),
    Column("flags", Text, nullable=False),
)
Index("ix_move_metric_definition_severity", move_metric.c.definition, move_metric.c.severity)
