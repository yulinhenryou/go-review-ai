"""Analysed turns in SQL: the `ResultStore` behind `CachedAnalyzer` (ADR-P03).

A stored turn comes back exactly as it was analysed: root values are
columns, candidates are JSON (moves as `[x, y]` or `"pass"`), and
ownership is little-endian float64 compressed with zlib, so every number
round-trips bit for bit (encoding version `ENCODING_VERSION`).

SQLAlchemy runs synchronously here; the async methods hand each call to a
worker thread so the event loop never waits on the database.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import struct
import zlib
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, Final, cast

import weiqi_core
from sqlalchemy import Connection, Engine, Table, func, select

from weiqi.engine import (
    Candidate,
    GameAnalysis,
    RootInfo,
    TurnAnalysis,
    TurnResult,
)
from weiqi.storage.schema import (
    ENCODING_VERSION,
    engine_identity,
    engine_query,
    position_eval,
)

if TYPE_CHECKING:
    from weiqi_core import Color, Move

    from weiqi.engine import EngineIdentity

_LOAD_BATCH: Final = 500
"""Keys per `IN (...)` lookup, well below every database's parameter limit."""


def hash_text(value: int) -> str:
    """A 128-bit position hash as 32 lowercase hex digits."""
    return f"{value:032x}"


# --- Encoding ---


def _move_json(move: Move) -> object:
    return move if move == "pass" else list(move)


def _move(value: object) -> Move:
    if value == "pass":
        return "pass"
    x, y = cast(list[int], value)
    return (x, y)


def encode_candidates(candidates: Iterable[Candidate]) -> str:
    return json.dumps(
        [
            {
                "move": _move_json(c.move),
                "order": c.order,
                "visits": c.visits,
                "winrate_black": c.winrate_black,
                "score_lead_black": c.score_lead_black,
                "prior": c.prior,
                "pv": [_move_json(m) for m in c.pv],
            }
            for c in candidates
        ],
        allow_nan=False,
        separators=(",", ":"),
    )


def decode_candidates(text: str) -> tuple[Candidate, ...]:
    return tuple(
        Candidate(
            move=_move(item["move"]),
            order=item["order"],
            visits=item["visits"],
            winrate_black=item["winrate_black"],
            score_lead_black=item["score_lead_black"],
            prior=item["prior"],
            pv=tuple(_move(m) for m in item["pv"]),
        )
        for item in json.loads(text)
    )


def encode_ownership(values: Sequence[float] | None) -> bytes | None:
    if values is None:
        return None
    return zlib.compress(struct.pack(f"<{len(values)}d", *values))


def decode_ownership(blob: bytes | None) -> tuple[float, ...] | None:
    if blob is None:
        return None
    raw = zlib.decompress(blob)
    return struct.unpack(f"<{len(raw) // 8}d", raw)


# --- The store ---


def insert_ignoring_duplicates(
    connection: Connection, table: Table, rows: list[dict[str, Any]]
) -> None:
    """Inserts rows, skipping any that would repeat a stored primary key or
    unique value. A result under an existing `query_key` answers the same
    question, so the first one stored is kept."""
    if connection.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        connection.execute(pg_insert(table).on_conflict_do_nothing(), rows)
    else:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        connection.execute(sqlite_insert(table).on_conflict_do_nothing(), rows)


def save_identity(connection: Connection, identity: EngineIdentity, now: datetime.datetime) -> str:
    """Stores `identity` unless it is stored already; returns its key."""
    identity_key = identity.identity_key()
    insert_ignoring_duplicates(
        connection,
        engine_identity,
        [
            {
                "identity_key": identity_key,
                "version": identity.version,
                "model_name": identity.model_name,
                "model_sha256": identity.model_sha256,
                "config_sha256": identity.config_sha256,
                "overrides": json.dumps([list(item) for item in identity.overrides]),
                "created_at": now,
            }
        ],
    )
    return identity_key


class SqlResultStore:
    """Stores analysed turns in the tables of `weiqi.storage.schema`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # The async interface (`ResultStore`).

    async def load(self, query_keys: Sequence[str]) -> dict[str, TurnResult]:
        return await asyncio.to_thread(self.load_sync, query_keys)

    async def save(self, analysis: GameAnalysis) -> None:
        await asyncio.to_thread(self.save_sync, analysis)

    # The same operations, blocking.

    def load_sync(self, query_keys: Sequence[str]) -> dict[str, TurnResult]:
        keys = list(dict.fromkeys(query_keys))
        found: dict[str, TurnResult] = {}
        with self._engine.connect() as connection:
            for start in range(0, len(keys), _LOAD_BATCH):
                batch = keys[start : start + _LOAD_BATCH]
                rows = connection.execute(
                    select(position_eval).where(position_eval.c.query_key.in_(batch))
                ).mappings()
                for row in rows:
                    if row["encoding"] != ENCODING_VERSION:
                        continue  # written by a format this code cannot read
                    found[row["query_key"]] = TurnResult(
                        analysis=TurnAnalysis(
                            turn=row["turn"],
                            root=RootInfo(
                                current_player=cast("Color", row["current_player"]),
                                visits=row["root_visits"],
                                winrate_black=row["winrate_black"],
                                score_lead_black=row["score_lead_black"],
                            ),
                            candidates=decode_candidates(row["candidates"]),
                            ownership_black=decode_ownership(row["ownership"]),
                        ),
                        query_key=row["query_key"],
                        engine_warnings=tuple(json.loads(row["engine_warnings"])),
                    )
        return found

    def save_sync(self, analysis: GameAnalysis) -> None:
        identity, request = analysis.identity, analysis.request
        now = datetime.datetime.now(datetime.UTC)
        with self._engine.begin() as connection:
            identity_key = save_identity(connection, identity, now)
            connection.execute(
                engine_query.insert(),
                {
                    "query_id": analysis.query_id,
                    "identity_key": identity_key,
                    "turn_count": len(analysis.results),
                    "elapsed_seconds": analysis.elapsed_seconds,
                    "created_at": now,
                },
            )
            allow_move = (
                None
                if request.allow_move is None
                else weiqi_core.to_gtp(request.allow_move, request.width, request.height)
            )
            rows = []
            for result in analysis.results:
                turn, root = result.analysis.turn, result.analysis.root
                stones, situation = request.hashes[turn]
                rows.append(
                    {
                        "query_key": result.query_key,
                        "query_id": analysis.query_id,
                        "turn": turn,
                        "stones_hash": hash_text(stones),
                        "situation_hash": hash_text(situation),
                        "current_player": root.current_player,
                        "max_visits": request.max_visits,
                        "root_visits": root.visits,
                        "winrate_black": root.winrate_black,
                        "score_lead_black": root.score_lead_black,
                        "candidates": encode_candidates(result.analysis.candidates),
                        "ownership": encode_ownership(result.analysis.ownership_black),
                        "engine_warnings": json.dumps(list(result.engine_warnings)),
                        "encoding": ENCODING_VERSION,
                        "created_at": now,
                        "allow_move": allow_move,
                    }
                )
            if rows:
                insert_ignoring_duplicates(connection, position_eval, rows)

    def query_keys_for_stones(self, stones_hash: int) -> list[str]:
        """Stored free searches whose stones match `stones_hash`, in any
        game. Such a turn may differ in move history, so it is a
        transposition, not an exact reuse (ADR-P03). Restricted searches are
        left out: they describe one move, not the position."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(position_eval.c.query_key)
                .where(position_eval.c.stones_hash == hash_text(stones_hash))
                .where(position_eval.c.allow_move.is_(None))
                .order_by(position_eval.c.query_key)
            )
            return [row[0] for row in rows]

    def counts(self) -> dict[str, int]:
        """Rows per table, for tests and diagnostics."""
        with self._engine.connect() as connection:
            return {
                table.name: connection.execute(select(func.count()).select_from(table)).scalar_one()
                for table in (engine_identity, engine_query, position_eval)
            }
