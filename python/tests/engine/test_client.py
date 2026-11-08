"""The supervised engine client against the fake engine (MIGRATION E03,
E05, E07, E08). A launcher script stands in for the `katago` binary and picks
the fake's mode for each start, so restarts can be tested."""

from __future__ import annotations

import asyncio
import hashlib
import os
import signal
import sys
from collections.abc import Coroutine
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from weiqi.engine import (
    AnalysisRequest,
    EngineProtocolError,
    EngineSettings,
    EngineTimeoutError,
    EngineUnavailableError,
    GameAnalysis,
    KataGoEngine,
    TurnResult,
)
from weiqi.engine.settings import DEFAULT_CONFIG, restart_delay

if TYPE_CHECKING:
    from weiqi_core import Color, Move

FAKE = Path(__file__).with_name("fake_katago.py")
MOVES: tuple[tuple[Color, Move], ...] = (("B", (3, 3)), ("W", (15, 15)), ("B", (15, 3)))
REQUEST = AnalysisRequest(
    width=19,
    height=19,
    rules="chinese",
    komi=7.5,
    moves=MOVES,
    analyze_turns=(0, 1, 2, 3),
    max_visits=8,
)


def run[T](coroutine: Coroutine[object, object, T]) -> T:
    return asyncio.run(asyncio.wait_for(coroutine, 20))


def settings(tmp_path: Path, *modes: str) -> EngineSettings:
    """Settings whose `katago` runs the fake in `modes[n]` on the n-th start
    (the last mode repeats)."""
    counter = tmp_path / "starts"
    branches = "\n".join(f"  {i}) mode={mode} ;;" for i, mode in enumerate(modes[:-1]))
    launcher = tmp_path / "katago"
    launcher.write_text(
        "#!/bin/sh\n"
        f'n=$(cat "{counter}" 2>/dev/null || echo 0)\n'
        f'echo $((n + 1)) > "{counter}"\n'
        f"case $n in\n{branches}\n  *) mode={modes[-1]} ;;\nesac\n"
        f'exec "{sys.executable}" "{FAKE}" "$mode" "$@"\n'
    )
    launcher.chmod(0o755)
    model, config = tmp_path / "model.bin.gz", tmp_path / "analysis.cfg"
    model.write_bytes(b"fixture model")
    config.write_text("fixture config\n")
    return EngineSettings(
        model_path=model,
        config_path=config,
        katago_path=str(launcher),
        restart_base_delay=0.01,
        restart_max_delay=0.02,
    )


async def stats(engine: KataGoEngine) -> dict[str, object]:
    # A test-only peek at the fake through the private process handle.
    process = engine._process
    assert process is not None
    return await process.request("fake_stats", timeout=5)


def test_readiness_reports_identity_without_paths(tmp_path: Path) -> None:
    # Prototype: test_readiness_and_no_local_paths_in_provenance.
    config = settings(tmp_path, "normal")

    async def scenario() -> tuple[dict[str, str], dict[str, object]]:
        async with KataGoEngine(config) as engine:
            return await engine.readiness(), await stats(engine)

    ready, seen = run(scenario())
    assert ready == {
        "status": "ready",
        "engine": "KataGo",
        "version": "1.16.4",
        "model_name": "fake-model",
        "model_sha256": hashlib.sha256(b"fixture model").hexdigest(),
        "config_sha256": hashlib.sha256(b"fixture config\n").hexdigest(),
    }
    assert "/" not in str(ready)
    argv = seen["argv"]
    assert isinstance(argv, list)
    assert argv[:2] == ["analysis", "-model"]
    assert argv[2] == str(config.model_path.resolve())
    overrides = argv[argv.index("-override-config") + 1]
    assert "reportAnalysisWinratesAs=BLACK" in overrides
    assert "logToStderr=false" in overrides and "logAllRequests=false" in overrides


def test_a_whole_game_is_one_query_with_keys_and_provenance(tmp_path: Path) -> None:
    seen: list[int] = []

    def on_turn(result: TurnResult) -> None:
        seen.append(result.analysis.turn)

    async def scenario() -> tuple[GameAnalysis, int, int]:
        async with KataGoEngine(settings(tmp_path, "normal")) as engine:
            analysis = await engine.analyze(REQUEST, on_turn=on_turn)
            return analysis, engine.queries, engine.starts

    analysis, queries, starts = run(scenario())
    assert (queries, starts) == (1, 1)
    assert sorted(seen) == [0, 1, 2, 3]
    assert [r.analysis.turn for r in analysis.results] == [0, 1, 2, 3]
    assert [r.analysis.root.current_player for r in analysis.results] == ["B", "W", "B", "W"]
    for result in analysis.results:
        assert result.query_key == REQUEST.query_key(analysis.identity, result.analysis.turn)
    assert analysis.raw_perspective == "BLACK"
    assert analysis.elapsed_seconds > 0
    assert len({r.query_key for r in analysis.results}) == 4


def test_the_engine_restarts_after_it_is_killed(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, int]:
        async with KataGoEngine(settings(tmp_path, "hang_all", "normal")) as engine:
            task = asyncio.create_task(engine.analyze(REQUEST))
            await asyncio.sleep(0.3)
            assert engine.pid is not None
            os.kill(engine.pid, signal.SIGKILL)
            with pytest.raises(EngineUnavailableError):
                await task
            analysis = await engine.analyze(REQUEST)
            return engine.starts, len(analysis.results)

    assert run(scenario()) == (2, 4)


def test_the_engine_restarts_after_a_crash(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, int]:
        async with KataGoEngine(settings(tmp_path, "crash", "normal")) as engine:
            with pytest.raises(EngineUnavailableError):
                await engine.analyze(REQUEST)
            analysis = await engine.analyze(REQUEST)
            return engine.starts, len(analysis.results)

    assert run(scenario()) == (2, 4)


def test_content_that_does_not_fit_retires_the_process(tmp_path: Path) -> None:
    async def scenario() -> int:
        async with KataGoEngine(settings(tmp_path, "wrong_player", "normal")) as engine:
            with pytest.raises(EngineProtocolError) as error:
                await engine.analyze(REQUEST)
            assert error.value.code == "root_player_mismatch"
            await engine.analyze(REQUEST)
            return engine.starts

    assert run(scenario()) == 2


def test_cancel_terminates_the_query_and_keeps_the_process(tmp_path: Path) -> None:
    async def scenario() -> tuple[dict[str, object], int]:
        async with KataGoEngine(settings(tmp_path, "hang_all")) as engine:
            task = asyncio.create_task(engine.analyze(REQUEST))
            await asyncio.sleep(0.3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return await stats(engine), engine.starts

    seen, starts = run(scenario())
    assert len(seen["terminated"]) == 1  # type: ignore[arg-type]
    assert starts == 1


def test_a_slow_game_times_out(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with KataGoEngine(settings(tmp_path, "hang_all")) as engine:
            with pytest.raises(EngineTimeoutError):
                await engine.analyze(REQUEST, timeout=0.2)

    run(scenario())


@pytest.mark.parametrize(
    ("mode", "code"), [("bad_version", "invalid_version"), ("two_models", "invalid_models")]
)
def test_readiness_failures_stop_the_start(tmp_path: Path, mode: str, code: str) -> None:
    async def scenario() -> int:
        engine = KataGoEngine(settings(tmp_path, mode))
        with pytest.raises(EngineProtocolError) as error:
            await engine.start()
        assert error.value.code == code
        await engine.close()
        return engine.starts

    assert run(scenario()) == 0


def test_a_missing_binary_or_model_is_unavailable(tmp_path: Path) -> None:
    # Prototype: test_missing_binary, test_missing_model.
    config = settings(tmp_path, "normal")

    async def start(changed: EngineSettings) -> str:
        with pytest.raises(EngineUnavailableError) as error:
            await KataGoEngine(changed).start()
        assert "/" not in str(error.value)
        return error.value.code

    missing_binary = replace(config, katago_path=str(tmp_path / "no-katago"))
    missing_model = replace(config, model_path=tmp_path / "missing.bin.gz")
    empty = tmp_path / "empty.bin.gz"
    empty.write_bytes(b"")
    assert run(start(missing_binary)) == "engine_not_found"
    assert run(start(missing_model)) == "engine_files_missing"
    assert run(start(replace(config, model_path=empty))) == "engine_files_missing"
    assert not (tmp_path / "starts").exists()  # no process was launched


def test_a_closed_engine_refuses_work(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = KataGoEngine(settings(tmp_path, "normal"))
        await engine.start()
        await engine.close()
        with pytest.raises(EngineUnavailableError):
            await engine.analyze(REQUEST)

    run(scenario())


def test_there_is_no_fallback_engine() -> None:
    # Prototype: test_default_engine_never_falls_back (ADR-007).
    with pytest.raises(EngineUnavailableError) as error:
        EngineSettings.from_environment({})
    assert error.value.code == "engine_not_configured"


def test_settings_come_from_the_environment() -> None:
    value = EngineSettings.from_environment(
        {"KATAGO_MODEL_PATH": "/models/m.bin.gz", "KATAGO_PATH": "/opt/katago"}
    )
    assert value.model_path == Path("/models/m.bin.gz")
    assert value.katago_path == "/opt/katago"
    assert value.config_path == DEFAULT_CONFIG
    assert DEFAULT_CONFIG.is_file()


def test_restart_delays_double_up_to_a_cap() -> None:
    assert [restart_delay(n, 0.5, 4.0) for n in range(6)] == [0.0, 0.5, 1.0, 2.0, 4.0, 4.0]
