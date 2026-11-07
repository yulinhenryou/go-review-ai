"""Golden conformance cases (ROADMAP M2 acceptance 1): the Python side.

Runs every case in testdata/conformance through the `weiqi_core` binding and
compares the transcript with the one the Rust runner recorded in
expected.json. The Rust runner also verifies the hand-written expectations,
so only equality is checked here. Text forms: testdata/conformance/README.md.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import weiqi_core as core

if TYPE_CHECKING:
    from weiqi_core import Color, Move, Point

CONFORMANCE = Path(__file__).resolve().parents[2] / "testdata" / "conformance"


def load(name: str) -> Any:
    return json.loads((CONFORMANCE / name).read_text(encoding="utf-8"))


EXPECTED = load("expected.json")
GAME_CASES = load("games.json")["cases"]
SGF_CASES = load("sgf.json")["cases"]

# --- Text forms ---


def point_text(point: Point) -> str:
    x, y = point
    return chr(ord("a") + x) + chr(ord("a") + y)


def parse_point(text: str) -> Point:
    return (ord(text[0]) - ord("a"), ord(text[1]) - ord("a"))


def move_text(color: Color, move: Move) -> str:
    return f"{color} {'pass' if move == 'pass' else point_text(move)}"


COLORS: dict[str, Color] = {"B": "B", "W": "W"}


def parse_move(text: str) -> tuple[Color, Move]:
    color, point = text.split(" ")
    return COLORS[color], "pass" if point == "pass" else parse_point(point)


def position_json(position: core.Position) -> dict[str, Any]:
    symbol = {None: ".", "B": "X", "W": "O"}
    width = position.width
    cells = position.cells
    return {
        "board": [
            "".join(symbol[cells[y * width + x]] for x in range(width))
            for y in range(position.height)
        ],
        "to_play": position.to_play,
        "ko_ban": None if position.ko_ban is None else point_text(position.ko_ban),
        "captures": {"black": position.captures.black, "white": position.captures.white},
        "consecutive_passes": position.consecutive_passes,
        "stones_hash": f"{position.stones_hash:032x}",
        "situation_hash": f"{position.situation_hash:032x}",
    }


def rules_json(rules: core.Rules) -> dict[str, Any]:
    return {
        "ko": rules.ko,
        "scoring": rules.scoring,
        "tax": rules.tax,
        "suicide": rules.suicide,
        "button": rules.button,
        "white_handicap_bonus": rules.white_handicap_bonus,
        "friendly_pass_ok": rules.friendly_pass_ok,
    }


# --- Game cases ---


def run_game(case: dict[str, Any]) -> dict[str, Any]:
    width, height = case["size"]
    rules = core.Rules.from_name(case["rules"])
    setup = None
    if "setup" in case:
        s = case["setup"]
        setup = core.Setup(
            [parse_point(p) for p in s["black"]],
            [parse_point(p) for p in s["white"]],
            s["to_play"],
        )
    game = core.Game(width, height, rules, case["komi"], setup)

    start = position_json(game.position())
    steps: list[dict[str, Any]] = []
    for entry in case["moves"]:
        text = entry if isinstance(entry, str) else entry["play"]
        color, move = parse_move(text)
        try:
            effect = game.play_as(color, move, case["mode"])
        except core.IllegalMoveError as error:
            steps.append({"move": text, "result": error.code})
            continue
        steps.append(
            {
                "move": text,
                "result": "ok",
                "captured": [point_text(p) for p in effect.captured],
                "suicided": [point_text(p) for p in effect.suicided],
                "violations": effect.violations,
                "repeated_position": effect.repeated_position,
                "position": position_json(game.position()),
            }
        )

    undo: list[dict[str, Any]] = []
    while (undone := game.undo()) is not None:
        undo.append(
            {
                "undone": move_text(*undone),
                "situation_hash": f"{game.position().situation_hash:032x}",
            }
        )
    return {"start": start, "steps": steps, "undo": undo}


# --- SGF cases ---


def record_json(record: core.GameRecord) -> dict[str, Any]:
    info = record.info
    setup = record.setup
    return {
        "size": [record.width, record.height],
        "rules": None if record.rules is None else rules_json(record.rules),
        "rules_text": record.rules_text,
        "komi": record.komi,
        "handicap": record.handicap,
        "setup": {
            "black": [point_text(p) for p in setup.black],
            "white": [point_text(p) for p in setup.white],
            "to_play": setup.to_play,
        },
        "moves": [move_text(color, move) for color, move in record.moves],
        "info": {
            "black_player": info.black_player,
            "white_player": info.white_player,
            "black_rank": info.black_rank,
            "white_rank": info.white_rank,
            "date": info.date,
            "event": info.event,
            "round": info.round,
            "place": info.place,
            "name": info.name,
            "result_text": info.result_text,
        },
    }


def sgf_game_json(tree: core.SgfTree, rules: core.Rules, komi: float) -> dict[str, Any]:
    try:
        record = core.extract(tree)
    except core.ExtractError as error:
        return {"extract_error": {"code": error.code, "node": error.node}}
    replay: dict[str, Any]
    try:
        result = record.replay(rules, komi)
    except core.ReplayError as error:
        replay = {"error": {"code": error.code, "move_number": error.move_number}}
    else:
        positions = result.positions
        replay = {
            "warnings": [{"move_number": w.move_number, "code": w.code} for w in result.warnings],
            "situation_hashes": [f"{p.situation_hash:032x}" for p in positions],
            "final": position_json(positions[-1]),
        }
    return {
        "record": record_json(record),
        "extract_warnings": [{"code": w.code, "node": w.node} for w in record.warnings],
        "replay": replay,
    }


def run_sgf(case: dict[str, Any]) -> dict[str, Any]:
    if "file" in case:
        data = (CONFORMANCE.parent / "sgf" / case["file"]).read_bytes()
    else:
        data = case["text"].encode("utf-8")
    rules = core.Rules.from_name(case["rules"])
    try:
        collection = core.parse_sgf(data)
    except core.SgfError as error:
        return {"error": {"code": error.code, "offset": error.offset}}
    return {
        "encoding": collection.encoding,
        "sgf_warnings": [{"code": w.code, "offset": w.offset} for w in collection.warnings],
        "games": [sgf_game_json(tree, rules, case["komi"]) for tree in collection.games],
    }


# --- Tests ---


def test_zobrist_version_matches_the_transcripts() -> None:
    assert EXPECTED["zobrist_version"] == core.ZOBRIST_VERSION


def test_every_case_has_a_transcript() -> None:
    assert sorted(c["name"] for c in GAME_CASES) == sorted(EXPECTED["games"])
    assert sorted(c["name"] for c in SGF_CASES) == sorted(EXPECTED["sgf"])


@pytest.mark.parametrize("case", GAME_CASES, ids=lambda c: c["name"])
def test_game_case_matches_rust(case: dict[str, Any]) -> None:
    assert run_game(case) == EXPECTED["games"][case["name"]]


@pytest.mark.parametrize("case", SGF_CASES, ids=lambda c: c["name"])
def test_sgf_case_matches_rust(case: dict[str, Any]) -> None:
    assert run_sgf(case) == EXPECTED["sgf"][case["name"]]
