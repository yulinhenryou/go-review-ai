"""Restricted searches of played moves through the cache, with the fake
engine and a real database (MIGRATION E04): sent together, stored under
their own keys, reused on a second review, and kept out of the position
index."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path

from test_cached_analysis import REQUEST, fake_settings

from weiqi.engine import CachedAnalysis, CachedAnalyzer, KataGoEngine
from weiqi.metrics import move_metrics, played_moves_to_search
from weiqi.review import search_played_moves
from weiqi.storage.results import SqlResultStore


def run[T](coroutine: Coroutine[object, object, T]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine, 30))


async def review(
    analyzer: CachedAnalyzer,
) -> tuple[CachedAnalysis, tuple[CachedAnalysis, ...]]:
    free = await analyzer.analyze(REQUEST)
    return free, await search_played_moves(analyzer, free)


def test_played_moves_are_searched_once_and_then_reused(
    tmp_path: Path, store: SqlResultStore
) -> None:
    settings = fake_settings(tmp_path)

    async def scenario() -> tuple[CachedAnalysis, tuple[CachedAnalysis, ...], int, int]:
        async with KataGoEngine(settings) as engine:
            analyzer = CachedAnalyzer(engine, store)
            free, searches = await review(analyzer)
            return free, searches, engine.queries, analyzer.hits

    free, searches, queries, hits = run(scenario())
    # The fake engine only ever proposes a pass without a score, so every
    # played move, the pass at turn 3 included, needs its own search.
    turns = played_moves_to_search(free)
    assert turns == (0, 1, 2, 3)
    assert [s.request.analyze_turns for s in searches] == [(t,) for t in turns]
    assert [s.request.allow_move for s in searches] == [m for _, m in REQUEST.moves]
    assert (queries, hits) == (1 + 4, 0)
    for item in move_metrics(free, searches):
        assert "separate_search" in item.same_root.flags
        assert "played_move_not_searched" not in item.same_root.flags
    assert store.counts()["position_eval"] == 5 + 4

    # A second review on a new engine process asks the engine nothing.
    again, again_searches, queries, hits = run(scenario())
    assert (queries, hits) == (0, 5 + 4)
    assert again.results == free.results
    assert [s.results for s in again_searches] == [s.results for s in searches]


def test_the_position_index_leaves_restricted_searches_out(
    tmp_path: Path, store: SqlResultStore
) -> None:

    async def scenario() -> CachedAnalysis:
        async with KataGoEngine(fake_settings(tmp_path)) as engine:
            free, _ = await review(CachedAnalyzer(engine, store))
            return free

    free = run(scenario())
    stones = REQUEST.hashes[1][0]
    assert store.query_keys_for_stones(stones) == [free.results[1].query_key]
