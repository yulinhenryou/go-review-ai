"""Stored reviews (MIGRATION R08; ROADMAP M4 acceptance 3, "persisted
results"): the result document comes back exactly, a game is stored once
per content, and the metric rows agree with the result they index."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from metric_fixtures import IDENTITY
from review_fixtures import ROOTS, SGF, review
from sqlalchemy import Engine, func, select

from weiqi.review import ReviewSettings, read_game
from weiqi.storage.migrate import upgrade
from weiqi.storage.reviews import SqlReviewStore
from weiqi.storage.schema import engine_identity, game, move_metric

SEQUENTIAL = "score_loss.sequential.v1"
SAME_ROOT = "score_loss.same_root.v1"


@pytest.fixture
def reviews(database: Engine) -> SqlReviewStore:
    upgrade(database)
    return SqlReviewStore(database)


def count(database: Engine, table: object) -> int:
    with database.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(table)).scalar_one())  # type: ignore[arg-type]


def test_a_review_comes_back_exactly_and_the_game_is_stored_once(
    reviews: SqlReviewStore, database: Engine
) -> None:
    result, settings = review(), ReviewSettings(max_visits=100)
    first = reviews.save_sync(read_game(SGF), result, IDENTITY, settings)
    partial = review([ROOTS[0], None, *ROOTS[2:]])
    second = reviews.save_sync(read_game(SGF), partial, IDENTITY, settings)
    assert reviews.result_json(first) == result.to_json()
    assert reviews.result_json(second) == partial.to_json()
    assert reviews.result_json("0" * 32) is None
    runs = reviews.runs(result.game.sgf_sha256)
    assert {r.run_id for r in runs} == {first, second}
    assert {r.status for r in runs} == {"complete", "partial"}
    assert len({r.game_id for r in runs}) == 1
    assert (runs[0].rules, runs[0].komi, runs[0].schema_version) == ("chinese", 7.5, "review.v1")
    assert reviews.sgf(result.game.sgf_sha256) == SGF
    assert count(database, game) == 1 and count(database, engine_identity) == 1


def test_metric_rows_agree_with_the_result(reviews: SqlReviewStore, database: Engine) -> None:
    result = review()
    run_id = reviews.save_sync(read_game(SGF), result, IDENTITY, ReviewSettings())
    with database.connect() as connection:
        rows = connection.execute(
            select(move_metric).where(move_metric.c.run_id == run_id)
        ).mappings()
        by_key = {(r["move_number"], r["definition"]): r for r in rows}
    assert len(by_key) == 2 * len(result.timeline)
    for item in result.timeline:
        primary, diagnostic = (
            by_key[item.move_number, SEQUENTIAL],
            by_key[item.move_number, SAME_ROOT],
        )
        assert (primary["score_loss"], primary["raw_score_loss"]) == (
            item.score_loss,
            item.raw_score_loss,
        )
        assert primary["severity"] == item.severity
        assert json.loads(primary["flags"]) == list(item.flags)
        assert diagnostic["severity"] is None
        assert json.loads(diagnostic["flags"]) == list(item.same_root_flags)
    # The kind of question profiles will ask in SQL: loss per colour.
    with database.connect() as connection:
        totals = dict(
            connection.execute(
                select(move_metric.c.color, func.sum(move_metric.c.score_loss))
                .where(move_metric.c.definition == SEQUENTIAL)
                .group_by(move_metric.c.color)
            ).all()
        )
    assert totals == {"B": 6.0, "W": 13.0}


def test_a_result_from_another_game_is_refused(reviews: SqlReviewStore) -> None:
    other = read_game(SGF.replace(b"PB[Alice]", b"PB[Carol]"))
    with pytest.raises(ValueError, match="belong"):
        reviews.save_sync(other, review(), IDENTITY, ReviewSettings())


def test_concurrent_saves_of_one_game_share_its_row(
    reviews: SqlReviewStore, database: Engine
) -> None:
    result = review()
    settings = replace(ReviewSettings(), mistake_limit=3)

    async def save_all() -> list[str]:
        return await asyncio.gather(
            *(reviews.save(read_game(SGF), result, IDENTITY, settings) for _ in range(4))
        )

    run_ids = asyncio.run(save_all())
    assert len(set(run_ids)) == 4
    assert count(database, game) == 1
    assert len(reviews.runs(result.game.sgf_sha256)) == 4
