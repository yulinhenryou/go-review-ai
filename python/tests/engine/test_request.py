"""Analysis requests: validation through the rules core, the KataGo query,
and the exact-reuse cache key of DECISIONS ADR-P03."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from weiqi.engine import AnalysisRequest, EngineIdentity, InvalidRequestError

if TYPE_CHECKING:
    from weiqi_core import Color, Move

MOVES: tuple[tuple[Color, Move], ...] = (
    ("B", (15, 3)),
    ("W", (3, 15)),
    ("B", (15, 15)),
    ("W", (3, 3)),
)
IDENTITY = EngineIdentity(
    version="1.16.4",
    model_name="fixture-model",
    model_sha256="a" * 64,
    config_sha256="b" * 64,
    overrides=(("reportAnalysisWinratesAs", "BLACK"),),
)


def request(**changes: object) -> AnalysisRequest:
    base = AnalysisRequest(
        width=19,
        height=19,
        rules="japanese",
        komi=6.5,
        moves=MOVES,
        analyze_turns=(0, 1, 2, 3, 4),
        max_visits=64,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def test_query_uses_gtp_vertices_and_sorted_setup() -> None:
    value = request(
        moves=(("W", (2, 2)),),
        analyze_turns=(0, 1),
        initial_black=((15, 3), (3, 15)),
        initial_player="W",
        include_ownership=True,
        override_settings=(("antiMirror", False), ("playoutDoublingAdvantage", 0)),
    ).to_query("q1")
    assert value == {
        "id": "q1",
        "boardXSize": 19,
        "boardYSize": 19,
        "rules": "japanese",
        "komi": 6.5,
        "initialStones": [["B", "D4"], ["B", "Q16"]],
        "initialPlayer": "W",
        "moves": [["W", "C17"]],
        "maxVisits": 64,
        "analysisPVLen": 8,
        "includeOwnership": True,
        "overrideSettings": {"antiMirror": False, "playoutDoublingAdvantage": 0},
        "analyzeTurns": [0, 1],
    }


def test_players_come_from_the_core_replay() -> None:
    assert request().players == ("B", "W", "B", "W", "B")
    # Record mode keeps an out-of-turn move; the opponent of the mover is next.
    moves: tuple[tuple[Color, Move], ...] = (("B", (3, 3)), ("B", (15, 15)), ("W", "pass"))
    assert request(moves=moves, analyze_turns=(3,)).players == ("B", "W", "W", "B")


def test_komi_is_stored_as_a_float() -> None:
    value = request(komi=7)
    assert value.komi == 7.0 and isinstance(value.komi, float)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"rules": "go-rules"}, "unknown_rules"),
        ({"komi": 0.3}, "invalid_komi"),
        ({"komi": True}, "invalid_komi"),
        ({"komi": "6.5"}, "invalid_komi"),
        ({"width": 0}, "unsupported_size"),
        ({"moves": (("B", (19, 0)),), "analyze_turns": (1,)}, "off_board"),
        ({"moves": (("B", (3, 3)), ("W", (3, 3))), "analyze_turns": (2,)}, "occupied"),
        ({"moves": (("X", (3, 3)),), "analyze_turns": (1,)}, "malformed_color"),
        ({"analyze_turns": ()}, "invalid_turns"),
        ({"analyze_turns": (2, 1)}, "invalid_turns"),
        ({"analyze_turns": (1, 1)}, "invalid_turns"),
        ({"analyze_turns": (5,)}, "invalid_turns"),
        ({"analyze_turns": (-1,)}, "invalid_turns"),
        ({"analyze_turns": (True,)}, "invalid_turns"),
        ({"max_visits": 0}, "invalid_max_visits"),
        ({"max_visits": 100_001}, "invalid_max_visits"),
        ({"max_visits": True}, "invalid_max_visits"),
        ({"pv_length": 0}, "invalid_pv_length"),
        ({"include_ownership": 1}, "invalid_ownership_flag"),
        ({"override_settings": (("x", float("nan")),)}, "invalid_setting"),
        ({"override_settings": (("x", 1), ("x", 2))}, "invalid_setting"),
        ({"override_settings": (("x", None),)}, "invalid_setting"),
    ],
)
def test_invalid_requests_are_rejected_with_codes(changes: dict[str, object], code: str) -> None:
    with pytest.raises(InvalidRequestError) as error:
        request(**changes)
    assert error.value.code == code


def test_query_key_hashes_a_canonical_document() -> None:
    # Keys sorted, no spaces, UTF-8. If this text changes, every stored cache
    # key changes, so QUERY_KEY_VERSION must be bumped with it.
    document = request().key_document(IDENTITY, 2)
    assert document == (
        '{"engine":{"config_sha256":"' + "b" * 64 + '","model_sha256":"' + "a" * 64 + '",'
        '"overrides":{"reportAnalysisWinratesAs":"BLACK"},"version":"1.16.4"},'
        '"format":1,'
        '"search":{"analysisPVLen":8,"boardXSize":19,"boardYSize":19,"includeOwnership":false,'
        '"initialPlayer":"B","initialStones":[],"komi":6.5,"maxVisits":64,'
        '"moves":[["B","Q16"],["W","D4"]],"overrideSettings":{},"rules":"japanese"}}'
    )
    assert request().query_key(IDENTITY, 2) == hashlib.sha256(document.encode()).hexdigest()


def test_query_key_ignores_what_does_not_change_the_search() -> None:
    key = request().query_key(IDENTITY, 2)
    # Later moves, the other analysed turns and the model's display name.
    later: tuple[tuple[Color, Move], ...] = (*MOVES[:2], ("B", (9, 9)))
    assert request(moves=later, analyze_turns=(2,)).query_key(IDENTITY, 2) == key
    assert request(analyze_turns=(2,)).query_key(IDENTITY, 2) == key
    renamed = replace(IDENTITY, model_name="another-name")
    assert request().query_key(renamed, 2) == key
    # Setup stones are a set; their order does not matter.
    setup = {"moves": (), "analyze_turns": (0,)}
    a = request(initial_black=((3, 3), (15, 15)), **setup).query_key(IDENTITY, 0)
    b = request(initial_black=((15, 15), (3, 3)), **setup).query_key(IDENTITY, 0)
    assert a == b


@pytest.mark.parametrize(
    "changes",
    [
        {"komi": 7.5},
        {"rules": "chinese"},
        {"max_visits": 65},
        {"pv_length": 9},
        {"include_ownership": True},
        {"initial_player": "W"},
        {"override_settings": (("antiMirror", True),)},
        {"width": 18, "height": 18},
    ],
)
def test_query_key_changes_with_every_search_setting(changes: dict[str, object]) -> None:
    assert request(**changes).query_key(IDENTITY, 0) != request().query_key(IDENTITY, 0)


@pytest.mark.parametrize(
    "identity",
    [
        replace(IDENTITY, version="1.16.5"),
        replace(IDENTITY, model_sha256="c" * 64),
        replace(IDENTITY, config_sha256="c" * 64),
        replace(IDENTITY, overrides=()),
    ],
)
def test_query_key_changes_with_the_engine(identity: EngineIdentity) -> None:
    assert request().query_key(identity, 4) != request().query_key(IDENTITY, 4)


def test_a_transposition_is_a_different_query() -> None:
    # Same stones after four moves, reached in another order: KataGo sees
    # the move history, so ADR-P03 keeps these as separate exact keys.
    swapped: tuple[tuple[Color, Move], ...] = (MOVES[2], MOVES[1], MOVES[0], MOVES[3])
    assert request(moves=swapped).query_key(IDENTITY, 4) != request().query_key(IDENTITY, 4)


def test_a_transposition_shares_the_stones_hash() -> None:
    # ...but the position index finds it (ADR-P03).
    swapped: tuple[tuple[Color, Move], ...] = (MOVES[2], MOVES[1], MOVES[0], MOVES[3])
    original, transposed = request().hashes, request(moves=swapped).hashes
    assert len(original) == len(MOVES) + 1
    assert transposed[4][0] == original[4][0]
    assert transposed[1][0] != original[1][0]


def test_identity_key_covers_every_field() -> None:
    key = IDENTITY.identity_key()
    assert len(key) == 64 and key == replace(IDENTITY).identity_key()
    # The model name is not part of query keys, but an identity row records it.
    renamed = replace(IDENTITY, model_name="other-name")
    assert renamed.key_fields() == IDENTITY.key_fields()
    assert renamed.identity_key() != key


def test_query_key_turn_must_exist() -> None:
    with pytest.raises(InvalidRequestError):
        request().query_key(IDENTITY, 5)


@pytest.mark.parametrize(
    "changes",
    [{"model_sha256": "A" * 64}, {"config_sha256": "abc"}, {"version": ""}],
)
def test_identity_is_validated(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidRequestError):
        replace(IDENTITY, **changes)  # type: ignore[arg-type]


def test_identity_holds_no_paths() -> None:
    # MIGRATION E08: provenance must not reveal the local file system.
    assert "/" not in repr(IDENTITY)
    assert set(IDENTITY.key_fields()) == {"version", "model_sha256", "config_sha256", "overrides"}
