"""Replays a recorded real KataGo exchange (MIGRATION E09, ROADMAP M3
acceptance 2). The fixture holds what KataGo 1.16.4 actually sent; these
tests check that today's code sends the same query and turns those replies
into exactly the recorded normalised results. They prove nothing about live
search; the opt-in tests in `tests/live/` do that."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import sys
from pathlib import Path

from weiqi.engine import EngineSettings, GameAnalysis, KataGoEngine, parse_turn
from weiqi.engine.client import BASE_OVERRIDES
from weiqi.engine.settings import DEFAULT_CONFIG
from weiqi.tools.record_engine import (
    REPO_ROOT,
    identity_from_document,
    jsonable,
    load_record,
    request_for_record,
)

FIXTURE = REPO_ROOT / "testdata" / "engine" / "short-game.json"
FAKE = Path(__file__).with_name("fake_katago.py")
DATA = json.loads(FIXTURE.read_text())
INPUT = DATA["input"]
REQUEST = request_for_record(
    load_record(REPO_ROOT / INPUT["sgf"]),
    rules=INPUT["rules"],
    komi=INPUT["komi"],
    max_visits=INPUT["max_visits"],
    pv_length=INPUT["pv_length"],
    include_ownership=INPUT["include_ownership"],
    analyze_turns=INPUT["analyze_turns"],
)
IDENTITY = identity_from_document(DATA["identity"])


def messages(direction: str) -> list[dict[str, object]]:
    return [e["message"] for e in DATA["exchange"] if e["direction"] == direction]


def analysis_replies() -> list[dict[str, object]]:
    return [m for m in messages("received") if "turnNumber" in m]


def test_the_fixture_matches_its_inputs() -> None:
    sgf = REPO_ROOT / INPUT["sgf"]
    assert hashlib.sha256(sgf.read_bytes()).hexdigest() == INPUT["sgf_sha256"]
    # Recorded with the committed config and the overrides the client forces.
    assert IDENTITY.config_sha256 == hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest()
    assert IDENTITY.overrides == BASE_OVERRIDES


def test_todays_query_is_the_recorded_query() -> None:
    sent = [m for m in messages("sent") if "action" not in m]
    assert len(sent) == 1
    assert REQUEST.to_query(str(sent[0]["id"])) == sent[0]


def test_replies_reproduce_every_normalised_field() -> None:
    replies = {int(str(m["turnNumber"])): m for m in analysis_replies()}
    assert sorted(replies) == list(REQUEST.analyze_turns)
    for stored in DATA["results"]:
        turn = stored["turn"]
        assert jsonable(parse_turn(replies[turn], REQUEST, turn)) == stored["analysis"]
        assert REQUEST.query_key(IDENTITY, turn) == stored["query_key"]
        assert stored["engine_warnings"] == []


def test_the_fixture_holds_no_local_paths() -> None:
    # Prototype: test_recorded_fixture_has_no_local_absolute_paths.
    text = FIXTURE.read_text()
    for marker in ("/Users/", "/home/", "/opt/", "/private/", "/tmp/", "/var/"):
        assert marker not in text
    for model in messages("received")[1]["models"]:  # type: ignore[attr-defined]
        assert "/" not in model["name"]


def test_the_whole_client_replays_the_exchange(tmp_path: Path) -> None:
    """The recording, played back by the fake engine, through process,
    client and parser: every turn comes back as recorded."""
    launcher = tmp_path / "katago"
    launcher.write_text(
        "#!/bin/sh\n"
        f"FAKE_KATAGO_REPLAY={shlex.quote(str(FIXTURE))} "
        f'exec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} replay "$@"\n'
    )
    launcher.chmod(0o755)
    model = tmp_path / "model.bin.gz"
    model.write_bytes(b"stand-in for the recorded model")
    settings = EngineSettings(model_path=model, katago_path=str(launcher))

    async def scenario() -> GameAnalysis:
        async with KataGoEngine(settings) as engine:
            return await engine.analyze(REQUEST)

    analysis = asyncio.run(asyncio.wait_for(scenario(), 20))
    assert [jsonable(r.analysis) for r in analysis.results] == [
        stored["analysis"] for stored in DATA["results"]
    ]
    # Only the model hash differs: the weights are not in the repository.
    identity = analysis.identity
    assert (identity.version, identity.model_name, identity.config_sha256) == (
        IDENTITY.version,
        IDENTITY.model_name,
        IDENTITY.config_sha256,
    )
