"""Stored turns come back exactly as analysed. The turns are the real
KataGo replies recorded in `testdata/engine/short-game.json`, so the round
trip covers real numbers, passes, PVs and ownership."""

from __future__ import annotations

import asyncio
import datetime
import json

import pytest
from sqlalchemy import Engine, update
from sqlalchemy.exc import IntegrityError

from weiqi.engine import GameAnalysis, TurnResult, parse_turn
from weiqi.storage.migrate import upgrade
from weiqi.storage.results import SqlResultStore, decode_ownership, encode_ownership
from weiqi.storage.schema import position_eval
from weiqi.tools.record_engine import (
    REPO_ROOT,
    identity_from_document,
    load_record,
    request_for_record,
)

DATA = json.loads((REPO_ROOT / "testdata" / "engine" / "short-game.json").read_text())
INPUT = DATA["input"]
REQUEST = request_for_record(
    load_record(REPO_ROOT / INPUT["sgf"]),
    rules=INPUT["rules"],
    komi=INPUT["komi"],
    max_visits=INPUT["max_visits"],
    include_ownership=True,
)
IDENTITY = identity_from_document(DATA["identity"])
REPLIES = {
    e["message"]["turnNumber"]: e["message"]
    for e in DATA["exchange"]
    if "turnNumber" in e["message"]
}


def recorded(query_id: str = "0" * 32) -> GameAnalysis:
    return GameAnalysis(
        request=REQUEST,
        identity=IDENTITY,
        query_id=query_id,
        results=tuple(
            TurnResult(
                analysis=parse_turn(REPLIES[turn], REQUEST, turn),
                query_key=REQUEST.query_key(IDENTITY, turn),
                engine_warnings=("boardXSize",) if turn == 2 else (),
            )
            for turn in REQUEST.analyze_turns
        ),
        elapsed_seconds=1.25,
    )


@pytest.fixture
def store(database: Engine) -> SqlResultStore:
    upgrade(database)
    return SqlResultStore(database)


def test_a_saved_game_loads_back_unchanged(store: SqlResultStore) -> None:
    analysis = recorded()
    asyncio.run(store.save(analysis))
    keys = [r.query_key for r in analysis.results]
    loaded = asyncio.run(store.load([*keys, "f" * 64]))  # an unknown key is left out
    assert set(loaded) == set(keys)
    for result in analysis.results:
        assert loaded[result.query_key] == result
    # The recording has "pass" candidates (turns 5 and 6), which round-trip too.
    assert any(c.move == "pass" for r in loaded.values() for c in r.analysis.candidates)
    assert store.counts() == {"engine_identity": 1, "engine_query": 1, "position_eval": 7}


def test_saving_the_same_turns_again_keeps_the_first_results(store: SqlResultStore) -> None:
    store.save_sync(recorded("1" * 32))
    store.save_sync(recorded("2" * 32))
    # One identity, both queries, but each position once.
    assert store.counts() == {"engine_identity": 1, "engine_query": 2, "position_eval": 7}


def test_positions_are_found_by_their_stones(store: SqlResultStore) -> None:
    store.save_sync(recorded())
    stones = [stones for stones, _ in REQUEST.hashes]
    # Turns 4 and 5 add only passes, so turns 4-6 share the stones of turn 4.
    assert stones[4] == stones[5] == stones[6]
    assert store.query_keys_for_stones(stones[4]) == sorted(
        REQUEST.query_key(IDENTITY, turn) for turn in (4, 5, 6)
    )
    assert store.query_keys_for_stones(stones[0]) == [REQUEST.query_key(IDENTITY, 0)]


def test_rows_in_an_unknown_encoding_are_not_used(store: SqlResultStore, database: Engine) -> None:
    store.save_sync(recorded())
    key = REQUEST.query_key(IDENTITY, 3)
    with database.begin() as connection:
        connection.execute(
            update(position_eval).where(position_eval.c.query_key == key).values(encoding=99)
        )
    assert key not in store.load_sync([key])


def test_foreign_keys_are_enforced(store: SqlResultStore, database: Engine) -> None:
    row = {
        "query_key": "a" * 64,
        "query_id": "no such query",
        "turn": 0,
        "stones_hash": "0" * 32,
        "situation_hash": "0" * 32,
        "current_player": "B",
        "max_visits": 1,
        "candidates": "[]",
        "engine_warnings": "[]",
        "encoding": 1,
        "created_at": datetime.datetime(2026, 11, 8, tzinfo=datetime.UTC),
    }
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(position_eval.insert(), row)


def test_ownership_round_trips_bit_for_bit() -> None:
    values = (0.1, -0.999999999, 1.0, -1.0, 0.0, 1e-300)
    assert decode_ownership(encode_ownership(values)) == values
    assert encode_ownership(None) is None and decode_ownership(None) is None
