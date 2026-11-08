"""The asyncio engine process against a fake JSON-lines engine (MIGRATION
E02, E06, E10). These tests check routing, failure handling and
cancellation, not real KataGo behaviour; live tests come later in M3."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Coroutine, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from weiqi.engine import (
    AnalysisRequest,
    EngineProtocolError,
    EngineRejectedError,
    EngineTimeoutError,
    EngineUnavailableError,
    parse_turn,
)
from weiqi.engine.process import LINE_LIMIT, EngineProcess, EngineReply

if TYPE_CHECKING:
    from weiqi_core import Color, Move

FAKE = Path(__file__).with_name("fake_katago.py")
MOVES: tuple[tuple[Color, Move], ...] = (("B", (3, 3)), ("W", (15, 15)), ("B", "pass"))
REQUEST = AnalysisRequest(
    width=19,
    height=19,
    rules="japanese",
    komi=6.5,
    moves=MOVES,
    analyze_turns=(0, 1, 2, 3),
    max_visits=8,
)


def run[T](coroutine: Coroutine[object, object, T]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine, 20))


async def start(
    mode: str = "normal", *, max_in_flight: int = 1, line_limit: int = LINE_LIMIT
) -> EngineProcess:
    return await EngineProcess.start(
        [sys.executable, str(FAKE), mode], max_in_flight=max_in_flight, line_limit=line_limit
    )


async def stats(engine: EngineProcess) -> dict[str, object]:
    return await engine.request("fake_stats", timeout=5)


def test_replies_are_routed_by_turn_and_parse() -> None:
    async def scenario() -> tuple[list[EngineReply], list[int], dict[str, object]]:
        seen: list[int] = []
        async with await start() as engine:
            version = await engine.request("query_version", timeout=5)
            replies = await engine.analyze(
                REQUEST.to_query("q1"), timeout=5, on_reply=lambda r: seen.append(r.turn)
            )
            return replies, seen, version

    replies, seen, version = run(scenario())
    assert version["version"] == "1.16.4"
    # The fake answers in reverse; results come back in turn order.
    assert seen == [3, 2, 1, 0]
    assert [reply.turn for reply in replies] == [0, 1, 2, 3]
    players = [parse_turn(r.payload, REQUEST, r.turn).root.current_player for r in replies]
    assert players == ["B", "W", "B", "W"]


def test_concurrent_queries_are_kept_apart() -> None:
    async def scenario() -> list[list[EngineReply]]:
        async with await start(max_in_flight=2) as engine:
            return await asyncio.gather(
                *(engine.analyze(REQUEST.to_query(f"q{i}"), timeout=5) for i in range(4))
            )

    for replies in run(scenario()):
        assert [reply.turn for reply in replies] == [0, 1, 2, 3]


def test_a_flood_on_stderr_does_not_block_replies() -> None:
    async def scenario() -> int:
        async with await start("stderr_flood") as engine:
            return len(await engine.analyze(REQUEST.to_query("q1"), timeout=10))

    assert run(scenario()) == 4


def test_progress_reports_are_skipped() -> None:
    async def scenario() -> list[EngineReply]:
        async with await start("during_search") as engine:
            return await engine.analyze(REQUEST.to_query("q1"), timeout=5)

    assert len(run(scenario())) == 4


def test_cancelling_terminates_the_query_and_keeps_the_engine() -> None:
    async def scenario() -> tuple[dict[str, object], int]:
        async with await start() as engine:
            task = asyncio.create_task(engine.analyze(REQUEST.to_query("hang-1")))
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            # The fake answers the terminate with late noResults replies,
            # which must be ignored; then the engine is still usable.
            after = await engine.analyze(REQUEST.to_query("q2"), timeout=5)
            return await stats(engine), len(after)

    seen, count = run(scenario())
    assert seen["terminated"] == ["hang-1"]
    assert count == 4


def test_a_timeout_terminates_the_query() -> None:
    async def scenario() -> tuple[dict[str, object], bool]:
        async with await start() as engine:
            with pytest.raises(EngineTimeoutError) as error:
                await engine.analyze(REQUEST.to_query("hang-2"), timeout=0.2)
            assert error.value.code == "engine_timeout"
            return await stats(engine), engine.alive

    seen, alive = run(scenario())
    assert seen["terminated"] == ["hang-2"] and alive


def test_an_engine_crash_fails_the_query_and_later_calls() -> None:
    async def scenario() -> None:
        async with await start("crash") as engine:
            with pytest.raises(EngineUnavailableError) as error:
                await engine.analyze(REQUEST.to_query("q1"), timeout=5)
            assert error.value.code == "engine_unavailable"
            assert not engine.alive
            with pytest.raises(EngineUnavailableError):
                await engine.analyze(REQUEST.to_query("q2"), timeout=5)

    run(scenario())


def test_killing_the_engine_fails_pending_queries() -> None:
    async def scenario() -> None:
        async with await start() as engine:
            task = asyncio.create_task(engine.analyze(REQUEST.to_query("hang-3")))
            await asyncio.sleep(0.2)
            os.kill(engine.pid, signal.SIGKILL)
            with pytest.raises(EngineUnavailableError):
                await task

    run(scenario())


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        ("garbage", "invalid_json"),
        ("nan", "invalid_json"),
        ("unknown_id", "unexpected_id"),
        ("bad_turn", "unexpected_turn"),
        ("duplicate", "duplicate_reply"),
        ("missing_marker", "missing_final_marker"),
        ("no_results", "no_results"),
        ("long_line", "line_too_long"),
    ],
)
def test_a_protocol_error_fails_the_query_and_stops_the_engine(mode: str, code: str) -> None:
    # Prototype: test_protocol_error_cleans_up_process.
    async def scenario() -> bool:
        async with await start(mode, line_limit=1024) as engine:
            with pytest.raises(EngineProtocolError) as error:
                await engine.analyze(REQUEST.to_query("q1"), timeout=5)
            assert error.value.code == code
            await asyncio.sleep(0.2)
            return engine.alive

    assert run(scenario()) is False


def test_a_rejected_query_leaves_the_engine_usable() -> None:
    async def scenario() -> int:
        async with await start("error") as engine:
            with pytest.raises(EngineRejectedError) as error:
                await engine.analyze(REQUEST.to_query("q1"), timeout=5)
            assert error.value.code == "engine_rejected"
            return len((await engine.request("query_models", timeout=5))["models"])  # type: ignore[arg-type]

    assert run(scenario()) == 1


def test_a_warning_about_rules_is_fatal_for_the_query() -> None:
    async def scenario() -> dict[str, object]:
        async with await start("warn_rules") as engine:
            with pytest.raises(EngineRejectedError) as error:
                await engine.analyze(REQUEST.to_query("q1"), timeout=5)
            assert error.value.code == "engine_warning"
            return await stats(engine)

    assert run(scenario())["terminated"] == ["q1"]


def test_other_warnings_are_kept_with_the_replies() -> None:
    async def scenario() -> list[EngineReply]:
        async with await start("warn_other") as engine:
            return await engine.analyze(REQUEST.to_query("q1"), timeout=5)

    assert {reply.warnings for reply in run(scenario())} == {("boardXSize",)}


def test_close_fails_pending_queries_and_removes_the_workdir() -> None:
    async def scenario() -> str:
        engine = await start()
        workdir = str((await stats(engine))["cwd"])
        task = asyncio.create_task(engine.analyze(REQUEST.to_query("hang-4")))
        await asyncio.sleep(0.2)
        await engine.close()
        await engine.close()  # idempotent
        with pytest.raises(EngineUnavailableError):
            await task
        return workdir

    workdir = run(scenario())
    assert Path(workdir).name.startswith("weiqi-engine-")
    assert not Path(workdir).exists()


def test_a_missing_binary_is_unavailable_without_naming_the_path() -> None:
    missing = "/no/such/directory/katago"
    with pytest.raises(EngineUnavailableError) as error:
        run(EngineProcess.start([missing, "analysis"]))
    assert error.value.code == "engine_unavailable"
    assert "/no/such" not in str(error.value)


def test_query_ids_cannot_be_reused() -> None:
    async def scenario() -> None:
        async with await start() as engine:
            await engine.analyze(REQUEST.to_query("q1"), timeout=5)
            task = asyncio.create_task(engine.analyze(REQUEST.to_query("hang-5")))
            await asyncio.sleep(0.2)
            with pytest.raises(ValueError, match="reused"):
                await engine.analyze(REQUEST.to_query("hang-5"), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    run(scenario())


def test_the_transcript_sees_every_message_in_order() -> None:
    seen: list[tuple[str, object, object]] = []

    def transcript(direction: str, message: Mapping[str, object]) -> None:
        seen.append((direction, message.get("id"), message.get("turnNumber")))

    async def scenario() -> None:
        engine = await EngineProcess.start([sys.executable, str(FAKE)], transcript=transcript)
        async with engine:
            await engine.analyze(REQUEST.to_query("q1"), timeout=5)
            task = asyncio.create_task(engine.analyze(REQUEST.to_query("hang-6")))
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await stats(engine)  # the terminate's late replies arrive before this answer

    run(scenario())
    assert seen[:5] == [("sent", "q1", None)] + [("received", "q1", t) for t in (3, 2, 1, 0)]
    assert seen[5] == ("sent", "hang-6", None)
    assert seen[6][0] == "sent"  # the terminate
    # Replies the process ignores are still in the transcript.
    assert [s for s in seen if s[1] == "hang-6" and s[0] == "received"] == [
        ("received", "hang-6", t) for t in (0, 1, 2, 3)
    ]
