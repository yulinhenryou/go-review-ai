"""Strict response parsing, ported from the prototype's
tests/test_katago_client.py (MIGRATION E01, E08). Each test keeps the intent
of a prototype assertion; the comments name it where the shape changed."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from weiqi.engine import (
    AnalysisRequest,
    EngineProtocolError,
    parse_turn,
    score_for,
    winrate_for,
)
from weiqi.engine.response import parse_candidate

if TYPE_CHECKING:
    from weiqi_core import Color

BASE = AnalysisRequest(
    width=19,
    height=19,
    rules="japanese",
    komi=6.5,
    moves=(("B", (15, 3)),),
    analyze_turns=(0, 1),
    max_visits=64,
)


def payload(color: Color, turn: int = 0) -> dict[str, object]:
    """A final response in BLACK perspective, like the prototype's fixture."""
    sign = 1 if color == "B" else -1
    return {
        "id": "q",
        "turnNumber": turn,
        "isDuringSearch": False,
        "rootInfo": {"currentPlayer": color, "visits": 64, "scoreLead": sign * 2.4, "winrate": 0.6},
        "moveInfos": [
            {
                "move": move,
                "order": i,
                "visits": 32,
                "scoreLead": sign * (2.4 - i * 0.7),
                "winrate": 0.58 - i * 0.03,
                "prior": 0.2,
                "pv": [move, "C3"],
            }
            for i, move in enumerate(["Q4", "D16", "D4"])
        ],
    }


@pytest.mark.parametrize(("color", "turn"), [("B", 0), ("W", 1)])
def test_values_stay_black_and_convert_in_one_place(color: Color, turn: int) -> None:
    # Prototype: test_candidate_score_perspective_and_real_pv, both colors.
    result = parse_turn(payload(color, turn), BASE, turn)
    best = result.candidates[0]
    assert best.move == (15, 15) and best.pv == ((15, 15), (2, 16))
    assert best.score_lead_black == (2.4 if color == "B" else -2.4)
    assert best.winrate_black == pytest.approx(0.58)
    assert score_for(color, best.score_lead_black) == 2.4
    assert winrate_for(color, best.winrate_black) == pytest.approx(0.58 if color == "B" else 0.42)
    assert result.root.current_player == color
    assert result.root.visits == 64


def test_missing_values_never_use_utility_or_fifty_percent() -> None:
    value = parse_candidate({"move": "Q16", "utility": 0.9}, BASE, 0)
    assert value.winrate_black is None and value.score_lead_black is None
    assert value.visits is None and value.prior is None and value.pv == ()
    assert winrate_for("W", None) is None and score_for("W", None) is None


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("scoreLead", float("nan"), "invalid_number"),
        ("scoreLead", float("inf"), "invalid_number"),
        ("scoreLead", True, "invalid_number"),
        ("scoreLead", "3", "invalid_number"),
        ("scoreLead", 10**1000, "invalid_number"),
        ("winrate", 1.1, "number_out_of_range"),
        ("winrate", -0.1, "number_out_of_range"),
        ("winrate", False, "invalid_number"),
        ("prior", 1.5, "number_out_of_range"),
        ("visits", -1, "invalid_visits"),
        ("visits", True, "invalid_visits"),
        ("visits", 2.0, "invalid_visits"),
        ("pv", "Q16", "invalid_pv"),
        ("pv", ["bad"], "invalid_coordinate"),
        ("pv", ["D4"], "pv_mismatch"),
        ("move", "Z19", "invalid_coordinate"),
        ("move", "I4", "invalid_coordinate"),
        ("move", "Q20", "invalid_coordinate"),
        ("move", None, "invalid_coordinate"),
    ],
)
def test_invalid_candidate_fields_are_rejected(field: str, value: object, code: str) -> None:
    info: dict[str, object] = {
        "move": "Q16",
        "scoreLead": 2,
        "winrate": 0.5,
        "visits": 20,
        "pv": ["Q16"],
    }
    info[field] = value
    with pytest.raises(EngineProtocolError) as error:
        parse_candidate(info, BASE, 0)
    assert error.value.code == code


def test_order_not_array_order_ranks_candidates() -> None:
    data = payload("B")
    data["moveInfos"] = list(reversed(data["moveInfos"]))  # type: ignore[call-overload]
    result = parse_turn(data, BASE, 0)
    assert [c.order for c in result.candidates] == [0, 1, 2]
    assert result.candidates[0].move == (15, 15)


def mutated(change: str) -> dict[str, object]:
    data = copy.deepcopy(payload("B"))
    infos: list[dict[str, object]] = data["moveInfos"]  # type: ignore[assignment]
    match change:
        case "duplicate_order":
            infos[1]["order"] = 0
        case "no_order_zero":
            data["moveInfos"] = infos[1:]
        case "bool_order":
            infos[0]["order"] = False
        case "missing_order":
            del infos[2]["order"]
        case "duplicate_move":
            infos[1]["move"] = "Q4"
            infos[1]["pv"] = ["Q4"]
        case "wrong_player":
            data["rootInfo"] = {"currentPlayer": "W"}
        case "no_root":
            del data["rootInfo"]
        case "infos_not_list":
            data["moveInfos"] = {"0": infos[0]}
        case "info_not_object":
            data["moveInfos"] = ["Q4"]
    return data


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("duplicate_order", "invalid_order"),
        ("no_order_zero", "invalid_order"),
        ("bool_order", "invalid_order"),
        ("missing_order", "invalid_order"),
        ("duplicate_move", "duplicate_candidate"),
        ("wrong_player", "root_player_mismatch"),
        ("no_root", "missing_root_info"),
        ("infos_not_list", "invalid_move_infos"),
        ("info_not_object", "invalid_move_infos"),
    ],
)
def test_malformed_responses_are_rejected(change: str, code: str) -> None:
    with pytest.raises(EngineProtocolError) as error:
        parse_turn(mutated(change), BASE, 0)
    assert error.value.code == code


def test_the_player_comes_from_the_request_replay() -> None:
    # Turn 1 follows a black move, so White must be the analysed player.
    with pytest.raises(EngineProtocolError) as error:
        parse_turn(payload("B", 1), BASE, 1)
    assert error.value.code == "root_player_mismatch"


def test_a_turn_that_was_not_requested_is_rejected() -> None:
    with pytest.raises(EngineProtocolError) as error:
        parse_turn(payload("B"), replace(BASE, analyze_turns=(1,)), 0)
    assert error.value.code == "unexpected_turn"


def test_empty_candidates_keep_only_the_root_value() -> None:
    # Prototype: test_empty_candidate_terminal_response_uses_only_root_value.
    data = payload("B")
    data["moveInfos"] = []
    result = parse_turn(data, BASE, 0)
    assert result.candidates == ()
    assert result.root.score_lead_black == 2.4


def test_root_values_may_be_missing() -> None:
    data = payload("B")
    data["rootInfo"] = {"currentPlayer": "B"}
    root = parse_turn(data, BASE, 0).root
    assert (root.visits, root.winrate_black, root.score_lead_black) == (None, None, None)


SMALL = AnalysisRequest(
    width=3,
    height=2,
    rules="chinese",
    komi=0.5,
    moves=(),
    analyze_turns=(0,),
    max_visits=8,
    include_ownership=True,
)


def small_payload(ownership: object) -> dict[str, object]:
    return {
        "rootInfo": {"currentPlayer": "B"},
        "moveInfos": [{"move": "B2", "order": 0, "pv": ["B2"]}],
        "ownership": ownership,
    }


def test_ownership_is_read_row_major_when_requested() -> None:
    values = [1, 0.5, 0, -0.25, -1, 0.75]
    result = parse_turn(small_payload(values), SMALL, 0)
    assert result.ownership_black == (1.0, 0.5, 0.0, -0.25, -1.0, 0.75)
    assert result.candidates[0].move == (1, 0)  # B2 is the top middle on 3x2


def test_missing_ownership_stays_missing() -> None:
    data = small_payload(None)
    assert parse_turn(data, SMALL, 0).ownership_black is None


@pytest.mark.parametrize(
    ("ownership", "code"),
    [
        ([0.0] * 5, "invalid_ownership"),
        ("0", "invalid_ownership"),
        ([0.0] * 5 + [1.5], "number_out_of_range"),
        ([0.0] * 5 + [float("nan")], "invalid_number"),
    ],
)
def test_invalid_ownership_is_rejected(ownership: object, code: str) -> None:
    with pytest.raises(EngineProtocolError) as error:
        parse_turn(small_payload(ownership), SMALL, 0)
    assert error.value.code == code


def test_ownership_that_was_not_requested_is_rejected() -> None:
    with pytest.raises(EngineProtocolError) as error:
        parse_turn(small_payload([0.0] * 6), replace(SMALL, include_ownership=False), 0)
    assert error.value.code == "unexpected_ownership"
