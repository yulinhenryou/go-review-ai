"""The fixture recorder's guards and sanitising (no engine needed)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from weiqi.engine import EngineSettings
from weiqi.tools.record_engine import (
    PUBLIC_SGF_DIR,
    Recorder,
    check_public,
    load_record,
    record,
    request_for_record,
)


def test_only_listed_public_records_may_be_recorded(tmp_path: Path) -> None:
    assert check_public(PUBLIC_SGF_DIR / "synthetic-short.sgf") == (
        "testdata/sgf/synthetic-short.sgf"
    )
    private = tmp_path / "my-game.sgf"
    private.write_text("(;SZ[19];B[pd])")
    with pytest.raises(ValueError, match="testdata/sgf"):
        check_public(private)
    with pytest.raises(ValueError, match="PROVENANCE"):
        check_public(PUBLIC_SGF_DIR / "not-listed.sgf")


def test_a_private_record_is_refused_before_the_engine_starts(tmp_path: Path) -> None:
    private = tmp_path / "my-game.sgf"
    private.write_text("(;SZ[19]RU[Japanese]KM[6.5];B[pd])")
    settings = EngineSettings(model_path=tmp_path / "none", katago_path=str(tmp_path / "none"))
    with pytest.raises(ValueError, match="testdata/sgf"):
        asyncio.run(
            record(
                private,
                settings,
                rules="japanese",
                komi=6.5,
                max_visits=8,
                pv_length=8,
                include_ownership=False,
            )
        )


def test_the_recorder_renumbers_ids_and_drops_model_directories() -> None:
    recorder = Recorder()
    recorder("sent", {"id": "f00d", "action": "query_models"})
    recorder(
        "received",
        {"id": "f00d", "models": [{"name": "/Users/someone/models/m.bin.gz"}]},
    )
    recorder("sent", {"id": "beef", "action": "terminate", "terminateId": "f00d"})
    assert recorder.exchange == [
        {"direction": "sent", "message": {"id": "id-1", "action": "query_models"}},
        {"direction": "received", "message": {"id": "id-1", "models": [{"name": "m.bin.gz"}]}},
        {
            "direction": "sent",
            "message": {"id": "id-2", "action": "terminate", "terminateId": "id-1"},
        },
    ]


def test_a_record_becomes_a_whole_game_request() -> None:
    request = request_for_record(
        load_record(PUBLIC_SGF_DIR / "synthetic-short.sgf"),
        rules="japanese",
        komi=6.5,
        max_visits=8,
    )
    assert request.analyze_turns == tuple(range(7))
    assert request.moves[-2:] == (("B", "pass"), ("W", "pass"))
    assert request.players == ("B", "W", "B", "W", "B", "W", "B")
