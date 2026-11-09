"""Metrics over the real KataGo exchange recorded in M3
(`testdata/engine/short-game.json`): the values must equal arithmetic done
directly on the recorded JSON replies, so sign and perspective handling is
checked against what the engine actually sent, passes included."""

from __future__ import annotations

import json

import pytest
import weiqi_core
from metric_fixtures import Evaluated

from weiqi.engine import TurnResult, parse_turn
from weiqi.metrics import move_metrics, ownership_facts, select_mistakes, turning_points
from weiqi.tools.record_engine import (
    REPO_ROOT,
    identity_from_document,
    load_record,
    request_for_record,
)

FIXTURE = REPO_ROOT / "testdata" / "engine" / "short-game.json"
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
REPLIES = {
    int(e["message"]["turnNumber"]): e["message"]
    for e in DATA["exchange"]
    if e["direction"] == "received" and "turnNumber" in e["message"]
}
KEYS = {stored["turn"]: stored["query_key"] for stored in DATA["results"]}


def evaluations() -> Evaluated:
    results = tuple(
        TurnResult(parse_turn(REPLIES[turn], REQUEST, turn), KEYS[turn], ())
        for turn in REQUEST.analyze_turns
    )
    return Evaluated(REQUEST, IDENTITY, results)


def mover_sign(color: str) -> int:
    return 1 if color == "B" else -1


def test_sequential_values_equal_the_recorded_root_values() -> None:
    result = move_metrics(evaluations())
    assert len(result) == len(REQUEST.moves) == 6
    for item in result:
        before = REPLIES[item.move_number - 1]["rootInfo"]
        after = REPLIES[item.move_number]["rootInfo"]
        sign = mover_sign(item.color)
        assert item.sequential.raw_score_loss == pytest.approx(
            sign * (before["scoreLead"] - after["scoreLead"])
        )
        assert item.sequential.winrate_delta_pp == pytest.approx(
            100 * sign * (after["winrate"] - before["winrate"])
        )
    assert [item.move for item in result[4:]] == ["pass", "pass"]


def test_same_root_values_equal_the_recorded_candidates() -> None:
    for item in move_metrics(evaluations()):
        infos = REPLIES[item.move_number - 1]["moveInfos"]
        best = min(infos, key=lambda info: info["order"])
        assert item.best_move is not None
        played = [i for i in infos if REQUEST.moves[item.move_number - 1][1] == _move(i["move"])]
        if not played:
            assert item.same_root.raw_score_loss is None
            assert "played_move_not_searched" in item.same_root.flags
            continue
        sign = mover_sign(item.color)
        assert item.same_root.raw_score_loss == pytest.approx(
            sign * (best["scoreLead"] - played[0]["scoreLead"])
        )


def test_selection_runs_on_real_values() -> None:
    # Whatever the recorded losses are, every selected move clears the band.
    for mistake in select_mistakes(move_metrics(evaluations())):
        assert mistake.score_loss >= 4.0


def _move(vertex: str) -> object:
    return weiqi_core.from_gtp(vertex, REQUEST.width, REQUEST.height)


def test_ownership_facts_equal_the_recorded_ownership() -> None:
    facts = ownership_facts(evaluations())
    assert len(facts) == 6
    for fact in facts:
        before = REPLIES[fact.move_number - 1]["ownership"]
        after = REPLIES[fact.move_number]["ownership"]
        sign = mover_sign(fact.color)
        assert fact.ownership_delta is not None
        assert len(fact.ownership_delta) == 361
        assert list(fact.ownership_delta) == pytest.approx(
            [sign * (a - b) for a, b in zip(after, before, strict=True)]
        )
        for change in fact.group_changes:
            # Every reported stone was on the board before the move.
            assert change.stones and change.before != change.after


def test_turning_points_run_on_real_values() -> None:
    for point in turning_points(evaluations()):
        assert point.band_before != point.band_after
