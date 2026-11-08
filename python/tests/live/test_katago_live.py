"""Live tests against the real KataGo (MIGRATION E13, ROADMAP M3 acceptance 3).

Opt in with `RUN_KATAGO_INTEGRATION=1` and the engine environment of
`EngineSettings.from_environment` (at least `KATAGO_MODEL_PATH`). Search is
not deterministic, so these tests check structure, provenance and signs with
wide margins, never exact values.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import signal
from collections.abc import Coroutine, Mapping
from typing import TYPE_CHECKING, Literal

import pytest

from weiqi.engine import (
    AnalysisRequest,
    EngineSettings,
    EngineUnavailableError,
    GameAnalysis,
    KataGoEngine,
    TurnResult,
)
from weiqi.tools.record_engine import REPO_ROOT, load_record, request_for_record

if TYPE_CHECKING:
    from weiqi_core import Color, Point

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_KATAGO_INTEGRATION") != "1",
    reason="real KataGo is opt-in: set RUN_KATAGO_INTEGRATION=1",
)

SHORT = REPO_ROOT / "testdata" / "sgf" / "synthetic-short.sgf"
LONG = REPO_ROOT / "testdata" / "sgf" / "maruyama-ito-1976.sgf"


def run[T](coroutine: Coroutine[object, object, T]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine, 900))


def short_request(rules: str = "japanese", visits: int = 32) -> AnalysisRequest:
    return request_for_record(
        load_record(SHORT), rules=rules, komi=6.5, max_visits=visits, include_ownership=True
    )


def long_request(visits: int, turns: tuple[int, ...] | None = None) -> AnalysisRequest:
    return request_for_record(
        load_record(LONG), rules="japanese", komi=5.5, max_visits=visits, analyze_turns=turns
    )


def check_traceable(analysis: GameAnalysis, settings: EngineSettings) -> None:
    """Every result names the engine that made it, and the turns are the ones asked for."""
    request, identity = analysis.request, analysis.identity
    assert identity.version and identity.model_name
    model = settings.model_path.read_bytes()
    assert identity.model_sha256 == hashlib.sha256(model).hexdigest()
    assert [r.analysis.turn for r in analysis.results] == list(request.analyze_turns)
    for result in analysis.results:
        turn, root = result.analysis.turn, result.analysis.root
        assert root.current_player == request.players[turn]
        assert root.visits is not None and root.visits > 0
        assert root.winrate_black is not None and root.score_lead_black is not None
        assert result.analysis.candidates
        assert result.query_key == request.query_key(identity, turn)
    assert len({r.query_key for r in analysis.results}) == len(analysis.results)


@pytest.mark.parametrize("rules", ["japanese", "chinese"])
def test_a_short_game_with_passes_is_traceable(rules: str) -> None:
    # Prototype: test_real_model_analysis_is_traceable_and_not_a_fixed_mock,
    # test_real_passes_and_end_of_record.
    settings = EngineSettings.from_environment()
    request = short_request(rules)

    async def scenario() -> GameAnalysis:
        async with KataGoEngine(settings) as engine:
            return await engine.analyze(request)

    analysis = run(scenario())
    check_traceable(analysis, settings)
    assert len(analysis.results) == 7  # six moves, the last two passes, and the end
    for result in analysis.results:
        ownership = result.analysis.ownership_black
        assert ownership is not None and len(ownership) == 19 * 19


def walls(owner: Color) -> tuple[list[Point], list[Point]]:
    """Black and white stones on 9x9: `owner` walls off columns 0-3 (36
    points), the other side columns 7-8 (18 points); column 5 is open."""
    big = [(4, y) for y in range(9)]
    small = [(6, y) for y in range(9)]
    return (big, small) if owner == "B" else (small, big)


@pytest.mark.parametrize("to_play", ["B", "W"])
@pytest.mark.parametrize("owner", ["B", "W"])
def test_values_are_from_blacks_perspective_whoever_is_to_move(
    owner: Color, to_play: Color
) -> None:
    """Winrate, score lead and ownership are all reported for Black
    (`reportAnalysisWinratesAs=BLACK`), not for the player to move.
    The side with the large area leads by about 18 points either way."""
    black, white = walls(owner)
    request = AnalysisRequest(
        width=9,
        height=9,
        rules="chinese",
        komi=0.5,
        moves=(),
        analyze_turns=(0,),
        max_visits=64,
        include_ownership=True,
        initial_black=tuple(black),
        initial_white=tuple(white),
        initial_player=to_play,
    )

    async def scenario() -> TurnResult:
        async with KataGoEngine(EngineSettings.from_environment()) as engine:
            return (await engine.analyze(request)).results[0]

    analysis = run(scenario()).analysis
    sign = 1 if owner == "B" else -1
    ownership = analysis.ownership_black
    assert ownership is not None

    def mean(columns: range) -> float:
        values = [ownership[y * 9 + x] for y in range(9) for x in columns]
        return sum(values) / len(values)

    assert analysis.root.current_player == to_play
    assert sign * mean(range(4)) > 0.5  # the owner's large area
    assert sign * mean(range(7, 9)) < -0.5  # the other side's small area
    assert analysis.root.score_lead_black is not None
    assert sign * analysis.root.score_lead_black > 5
    assert analysis.root.winrate_black is not None
    assert (
        (analysis.root.winrate_black > 0.9) if owner == "B" else (analysis.root.winrate_black < 0.1)
    )


def test_the_235_move_game_completes_with_provenance() -> None:
    settings = EngineSettings.from_environment()
    request = long_request(visits=32)
    seen: list[int] = []

    async def scenario() -> tuple[GameAnalysis, int, int]:
        async with KataGoEngine(settings) as engine:
            analysis = await engine.analyze(request, on_turn=lambda r: seen.append(r.analysis.turn))
            return analysis, engine.queries, engine.starts

    analysis, queries, starts = run(scenario())
    assert (queries, starts) == (1, 1)  # one query for the whole game, one process
    assert len(request.moves) == 235 and len(analysis.results) == 236
    assert sorted(seen) == list(range(236))  # progress for every turn
    check_traceable(analysis, settings)


def test_cancel_terminates_the_query_and_keeps_the_process() -> None:
    # Prototype: test_real_running_job_cancel_reaps_engine_and_allows_next_job.
    # The new adapter keeps the warm process instead of reaping it.
    sent: list[Mapping[str, object]] = []
    received: list[Mapping[str, object]] = []

    def transcript(direction: Literal["sent", "received"], message: Mapping[str, object]) -> None:
        (sent if direction == "sent" else received).append(message)

    slow = long_request(visits=100_000, turns=(100, 101))

    async def scenario() -> tuple[int | None, int, int | None, GameAnalysis]:
        async with KataGoEngine(EngineSettings.from_environment(), transcript=transcript) as engine:
            pid = engine.pid
            task = asyncio.create_task(engine.analyze(slow))
            await asyncio.sleep(1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            query_id = next(m["id"] for m in sent if "analyzeTurns" in m)

            def closed() -> set[object]:
                return {
                    m["turnNumber"]
                    for m in received
                    if m.get("id") == query_id and m.get("isDuringSearch") is False
                }

            # KataGo answers the terminate by closing every turn of the query.
            async with asyncio.timeout(10):
                while closed() != {100, 101}:
                    await asyncio.sleep(0.05)
            assert any(m.get("terminateId") == query_id for m in sent)
            after = await engine.analyze(short_request(visits=16))
            return pid, engine.starts, engine.pid, after

    pid, starts, pid_after, after = run(scenario())
    assert starts == 1 and pid_after == pid
    assert len(after.results) == 7


def test_a_killed_engine_fails_the_query_and_is_restarted() -> None:
    async def scenario() -> tuple[int | None, int | None, int, GameAnalysis]:
        async with KataGoEngine(EngineSettings.from_environment()) as engine:
            first = engine.pid
            assert first is not None
            task = asyncio.create_task(engine.analyze(long_request(100_000, (100, 101))))
            await asyncio.sleep(1.0)
            os.kill(first, signal.SIGKILL)
            with pytest.raises(EngineUnavailableError):
                await task
            after = await engine.analyze(short_request(visits=16))
            return first, engine.pid, engine.starts, after

    first, second, starts, after = run(scenario())
    assert starts == 2 and second is not None and second != first
    assert len(after.results) == 7
