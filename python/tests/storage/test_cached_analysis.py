"""The cache in front of the engine (ROADMAP M3 acceptance 4), with the fake
engine and a real database: a repeated request asks the engine nothing."""

from __future__ import annotations

import asyncio
import shlex
import sys
from collections.abc import Coroutine, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest

from weiqi.engine import (
    AnalysisRequest,
    CachedAnalysis,
    CachedAnalyzer,
    EngineSettings,
    EngineUnavailableError,
    KataGoEngine,
)
from weiqi.storage.results import SqlResultStore

FAKE = Path(__file__).parents[1] / "engine" / "fake_katago.py"
REQUEST = AnalysisRequest(
    width=19,
    height=19,
    rules="chinese",
    komi=7.5,
    moves=(("B", (3, 3)), ("W", (15, 15)), ("B", (15, 3)), ("W", "pass")),
    analyze_turns=(0, 1, 2, 3, 4),
    max_visits=8,
)


def run[T](coroutine: Coroutine[object, object, T]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine, 20))


def fake_settings(tmp_path: Path, mode: str = "normal") -> EngineSettings:
    launcher = tmp_path / "katago"
    launcher.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} {mode} "$@"\n'
    )
    launcher.chmod(0o755)
    model, config = tmp_path / "model.bin.gz", tmp_path / "analysis.cfg"
    model.write_bytes(b"fixture model")
    config.write_text("fixture config\n")
    return EngineSettings(model_path=model, config_path=config, katago_path=str(launcher))


def test_a_repeated_request_is_answered_from_the_store(
    tmp_path: Path, store: SqlResultStore
) -> None:
    async def scenario() -> tuple[CachedAnalysis, CachedAnalysis, CachedAnalyzer, int]:
        async with KataGoEngine(fake_settings(tmp_path)) as engine:
            analyzer = CachedAnalyzer(engine, store)
            first = await analyzer.analyze(REQUEST)
            second = await analyzer.analyze(REQUEST)
            return first, second, analyzer, engine.queries

    first, second, analyzer, queries = run(scenario())
    assert first.cached_turns == () and first.engine_analysis is not None
    assert second.cached_turns == REQUEST.analyze_turns and second.engine_analysis is None
    assert second.results == first.results
    assert (analyzer.misses, analyzer.hits, queries) == (5, 5, 1)


def test_the_store_outlives_the_engine_process(tmp_path: Path, store: SqlResultStore) -> None:
    settings = fake_settings(tmp_path)

    async def analyze_once() -> tuple[int, int]:
        async with KataGoEngine(settings) as engine:
            analyzer = CachedAnalyzer(engine, store)
            await analyzer.analyze(REQUEST)
            return analyzer.hits, engine.queries

    # Same engine files, so the same identity and the same keys.
    assert run(analyze_once()) == (0, 1)
    assert run(analyze_once()) == (5, 0)


def test_only_missing_turns_are_sent(tmp_path: Path, store: SqlResultStore) -> None:
    sent: list[Mapping[str, object]] = []

    def transcript(direction: Literal["sent", "received"], message: Mapping[str, object]) -> None:
        if direction == "sent" and "analyzeTurns" in message:
            sent.append(message)

    async def scenario() -> CachedAnalysis:
        async with KataGoEngine(fake_settings(tmp_path), transcript=transcript) as engine:
            analyzer = CachedAnalyzer(engine, store)
            await analyzer.analyze(replace(REQUEST, analyze_turns=(0, 1, 2)))
            return await analyzer.analyze(REQUEST)

    result = run(scenario())
    assert [m["analyzeTurns"] for m in sent] == [[0, 1, 2], [3, 4]]
    assert result.cached_turns == (0, 1, 2)
    assert [r.analysis.turn for r in result.results] == [0, 1, 2, 3, 4]


def test_a_different_search_is_not_reused(tmp_path: Path, store: SqlResultStore) -> None:
    async def scenario() -> tuple[int, int]:
        async with KataGoEngine(fake_settings(tmp_path)) as engine:
            analyzer = CachedAnalyzer(engine, store)
            await analyzer.analyze(REQUEST)
            await analyzer.analyze(replace(REQUEST, max_visits=16))
            return analyzer.hits, engine.queries

    assert run(scenario()) == (0, 2)


def test_a_failed_query_stores_nothing(tmp_path: Path, store: SqlResultStore) -> None:
    async def scenario() -> None:
        async with KataGoEngine(fake_settings(tmp_path, "crash")) as engine:
            with pytest.raises(EngineUnavailableError):
                await CachedAnalyzer(engine, store).analyze(REQUEST)

    run(scenario())
    assert store.counts()["position_eval"] == 0


def test_progress_reports_stored_turns_too(tmp_path: Path, store: SqlResultStore) -> None:
    seen: list[int] = []

    async def scenario() -> None:
        async with KataGoEngine(fake_settings(tmp_path)) as engine:
            analyzer = CachedAnalyzer(engine, store)
            await analyzer.analyze(replace(REQUEST, analyze_turns=(1, 3)))
            await analyzer.analyze(REQUEST, on_turn=lambda r: seen.append(r.analysis.turn))

    run(scenario())
    assert seen[:2] == [1, 3]  # stored turns first
    assert sorted(seen) == [0, 1, 2, 3, 4]
