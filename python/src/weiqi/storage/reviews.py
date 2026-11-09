"""Finished reviews in SQL (MIGRATION R08; ARCHITECTURE §10.3).

A review is stored as three things: the SGF file once per content
(`game`), the run with its settings and canonical result JSON
(`review_run`), and per-move score-loss rows (`move_metric`) that later
milestones aggregate in SQL. The result JSON is the record of what the
review said; the metric rows are an index into it and never disagree with
it, because both are written from the same `ReviewResult` in one
transaction.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import uuid
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, Engine, select

from weiqi.storage.results import insert_ignoring_duplicates, save_identity
from weiqi.storage.schema import game, move_metric, review_run

if TYPE_CHECKING:
    from weiqi.engine import EngineIdentity
    from weiqi.review import GameInput, ReviewResult, ReviewSettings


@dataclass(frozen=True, slots=True)
class StoredRun:
    """One stored review run, without its result document."""

    run_id: str
    game_id: str
    rules: str
    komi: float
    status: str
    schema_version: str
    created_at: datetime.datetime


def _game_id(connection: Connection, sgf: bytes, sgf_sha256: str, now: datetime.datetime) -> str:
    """The id of the stored game with this content, storing it if new. Two
    concurrent saves of the same file both end with the one stored row."""
    insert_ignoring_duplicates(
        connection,
        game,
        [{"game_id": uuid.uuid4().hex, "sgf_sha256": sgf_sha256, "sgf": sgf, "created_at": now}],
    )
    return str(
        connection.execute(
            select(game.c.game_id).where(game.c.sgf_sha256 == sgf_sha256)
        ).scalar_one()
    )


def _metric_rows(run_id: str, result: ReviewResult) -> list[dict[str, Any]]:
    """Two rows per move: the primary (sequential) definition with its
    severity, and the same-root diagnostic, which has no severity."""
    rows = []
    for item in result.timeline:
        rows.append(
            {
                "run_id": run_id,
                "move_number": item.move_number,
                "definition": result.method.score_loss,
                "color": item.color,
                "raw_score_loss": item.raw_score_loss,
                "score_loss": item.score_loss,
                "winrate_delta_pp": item.winrate_delta_pp,
                "severity": item.severity,
                "flags": json.dumps(list(item.flags)),
            }
        )
        rows.append(
            {
                "run_id": run_id,
                "move_number": item.move_number,
                "definition": result.method.score_loss_diagnostic,
                "color": item.color,
                "raw_score_loss": item.same_root_raw_score_loss,
                "score_loss": item.same_root_score_loss,
                "winrate_delta_pp": item.same_root_winrate_delta_pp,
                "severity": None,
                "flags": json.dumps(list(item.same_root_flags)),
            }
        )
    return rows


class SqlReviewStore:
    """Stores reviews in the tables of `weiqi.storage.schema`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def save(
        self,
        game_input: GameInput,
        result: ReviewResult,
        identity: EngineIdentity,
        settings: ReviewSettings,
    ) -> str:
        return await asyncio.to_thread(self.save_sync, game_input, result, identity, settings)

    def save_sync(
        self,
        game_input: GameInput,
        result: ReviewResult,
        identity: EngineIdentity,
        settings: ReviewSettings,
    ) -> str:
        """Stores one review of `game_input` and returns its run id."""
        if result.game.sgf_sha256 != game_input.sgf_sha256:
            raise ValueError("the result does not belong to this game")
        now = datetime.datetime.now(datetime.UTC)
        run_id = uuid.uuid4().hex
        with self._engine.begin() as connection:
            identity_key = save_identity(connection, identity, now)
            game_id = _game_id(connection, game_input.sgf, game_input.sgf_sha256, now)
            connection.execute(
                review_run.insert(),
                {
                    "run_id": run_id,
                    "game_id": game_id,
                    "identity_key": identity_key,
                    "rules": result.game.rules,
                    "komi": result.game.komi,
                    "settings": json.dumps(asdict(settings), sort_keys=True, allow_nan=False),
                    "schema_version": result.schema,
                    "status": result.status,
                    "result": result.to_json(),
                    "created_at": now,
                },
            )
            rows = _metric_rows(run_id, result)
            if rows:
                connection.execute(move_metric.insert(), rows)
        return run_id

    def result_json(self, run_id: str) -> str | None:
        """The stored result document of a run, exactly as saved."""
        with self._engine.connect() as connection:
            value = connection.execute(
                select(review_run.c.result).where(review_run.c.run_id == run_id)
            ).scalar_one_or_none()
        return None if value is None else str(value)

    def runs(self, sgf_sha256: str) -> list[StoredRun]:
        """The stored runs of the game with this content, oldest first."""
        query = (
            select(review_run)
            .join(game, game.c.game_id == review_run.c.game_id)
            .where(game.c.sgf_sha256 == sgf_sha256)
            .order_by(review_run.c.created_at, review_run.c.run_id)
        )
        with self._engine.connect() as connection:
            return [
                StoredRun(
                    run_id=row["run_id"],
                    game_id=row["game_id"],
                    rules=row["rules"],
                    komi=row["komi"],
                    status=row["status"],
                    schema_version=row["schema_version"],
                    created_at=row["created_at"],
                )
                for row in connection.execute(query).mappings()
            ]

    def sgf(self, sgf_sha256: str) -> bytes | None:
        """The stored SGF bytes with this hash."""
        with self._engine.connect() as connection:
            value = connection.execute(
                select(game.c.sgf).where(game.c.sgf_sha256 == sgf_sha256)
            ).scalar_one_or_none()
        return None if value is None else bytes(value)
