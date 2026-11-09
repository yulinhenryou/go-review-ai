"""What a review accepts (MIGRATION G04, G05): one game, confirmed rules and
komi with no defaults, and the inputs the prototype could not read."""

from __future__ import annotations

import pytest

from weiqi.engine import InvalidRequestError
from weiqi.review import (
    ReviewInputError,
    confirm,
    read_game,
    recorded_rules,
    replay_warnings,
    review_request,
)
from weiqi.tools.record_engine import REPO_ROOT

CORPUS = REPO_ROOT / "testdata" / "sgf"


def test_rules_and_komi_come_from_the_record_when_recognised() -> None:
    g = read_game((CORPUS / "sample-game.sgf").read_bytes())
    assert recorded_rules(g.record) == "japanese"
    assert confirm(g) == ("japanese", 6.5)
    # The caller's confirmation wins over the record.
    assert confirm(g, "chinese", 7.5) == ("chinese", 7.5)


def test_missing_metadata_is_never_filled_in() -> None:
    # Prototype: require_metadata; the browser confirmation fixture.
    g = read_game((CORPUS / "m4-missing-metadata.sgf").read_bytes())
    with pytest.raises(ReviewInputError) as error:
        confirm(g)
    assert (error.value.code, error.value.field) == ("metadata_unconfirmed", "rules")
    with pytest.raises(ReviewInputError) as error:
        confirm(g, rules="chinese")
    assert (error.value.code, error.value.field) == ("metadata_unconfirmed", "komi")
    assert confirm(g, "chinese", 7.5) == ("chinese", 7.5)


@pytest.mark.parametrize("ru", ["", "RU[]", "RU[Ing]", "RU[GOE]"])
def test_unknown_or_empty_rules_need_confirmation(ru: str) -> None:
    g = read_game(f"(;FF[4]GM[1]SZ[19]{ru}KM[7.5];B[pd])".encode())
    assert recorded_rules(g.record) is None
    with pytest.raises(ReviewInputError):
        confirm(g)


@pytest.mark.parametrize(
    ("ru", "name"), [("Chinese", "chinese"), ("JAPANESE", "japanese"), ("NZ", "new-zealand")]
)
def test_recognised_rule_names(ru: str, name: str) -> None:
    g = read_game(f"(;FF[4]GM[1]SZ[19]RU[{ru}]KM[7.5];B[pd])".encode())
    assert recorded_rules(g.record) == name


def test_only_known_rule_sets_can_be_confirmed() -> None:
    g = read_game((CORPUS / "sample-game.sgf").read_bytes())
    with pytest.raises(ReviewInputError) as error:
        confirm(g, rules="ing")
    assert error.value.code == "invalid_rules"


@pytest.mark.parametrize(
    ("result", "status"),
    [
        ("RE[W+R]", "result_recorded"),
        ("RE[?]", "unfinished_or_unknown"),
        ("", "unfinished_or_unknown"),
    ],
)
def test_a_recorded_result_is_metadata_not_completeness(result: str, status: str) -> None:
    # Prototype: test_pass_is_not_a_missing_move_and_result_metadata_is_not_inferred.
    g = read_game(f"(;FF[4]GM[1]SZ[19]{result};B[pd])".encode())
    assert g.record_status == status


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("(;FF[4]GM[1]SZ[19];B[pd])(;FF[4]GM[1]SZ[19];B[dd])", "multiple_games"),
        ("not an sgf at all", None),
    ],
)
def test_files_that_are_not_one_game_are_rejected(text: str, code: str | None) -> None:
    with pytest.raises(ReviewInputError) as error:
        read_game(text.encode())
    if code is not None:
        assert error.value.code == code


def test_an_impossible_move_is_rejected_before_the_engine() -> None:
    # Prototype fixture m4-invalid.sgf: White plays on Black's stone.
    g = read_game((CORPUS / "m4-invalid.sgf").read_bytes())
    with pytest.raises(InvalidRequestError) as error:
        review_request(g, *confirm(g), max_visits=10)
    assert error.value.code == "occupied"


def test_inputs_the_prototype_could_not_read() -> None:
    # A GBK file without CA, and a file with 110 commentary variations: the
    # main line is reviewed and the reader says what it noticed.
    gbk = read_game((CORPUS / "kejie-2025-11-27-gbk.sgf").read_bytes())
    utf8 = read_game((CORPUS / "kejie-2025-11-27.sgf").read_bytes())
    assert gbk.encoding == "gb18030" and "encoding_guessed" in gbk.input_warnings
    assert "first_variation_only" in utf8.input_warnings
    assert gbk.record.moves == utf8.record.moves and len(utf8.record.moves) == 111
    # Setup stones (handicap) reach the request.
    handicap = read_game(b"(;FF[4]GM[1]SZ[19]HA[2]AB[pd][dp]RU[Japanese]KM[0.5];W[dd])")
    request = review_request(handicap, *confirm(handicap), max_visits=10)
    assert request.initial_black == ((3, 15), (15, 3))
    assert request.initial_player == "W" and request.players[0] == "W"
    assert request.include_ownership and request.analyze_turns == (0, 1)


@pytest.mark.parametrize(
    ("moves", "rules", "code", "number"),
    [
        # A ko recaptured at once, with a tenuki before the first capture.
        (
            "B[gf];W[hf];B[fg];W[ig];B[gh];W[hh];B[pd];W[gg];B[hg];W[gg]",
            "japanese",
            "ko_violation",
            10,
        ),
        ("B[ba];W[pd];B[ab];W[aa]", "chinese", "suicide", 4),
        ("B[pd];B[dd]", "chinese", "out_of_turn", 2),
    ],
)
def test_a_record_that_breaks_the_rules_is_refused_with_its_move(
    moves: str, rules: str, code: str, number: int
) -> None:
    # ADR-P19: the prototype refused these too; KataGo refuses suicide.
    g = read_game(f"(;FF[4]GM[1]SZ[19];{moves})".encode())
    assert replay_warnings(g, rules, 7.5) == ((number, code),)
    with pytest.raises(ReviewInputError) as error:
        review_request(g, rules, 7.5, max_visits=10)
    assert (error.value.code, error.value.move_number, error.value.field) == (code, number, "moves")


def test_play_after_two_passes_and_empty_games() -> None:
    # Resumption breaks no rule (the prototype refused it as unsupported).
    resumed = read_game(b"(;FF[4]GM[1]SZ[19];B[pd];W[];B[];W[dd])")
    assert review_request(resumed, "japanese", 6.5, max_visits=10).analyze_turns == (0, 1, 2, 3, 4)
    empty = read_game(b"(;FF[4]GM[1]SZ[19]RU[Chinese]KM[7.5])")
    with pytest.raises(ReviewInputError) as error:
        review_request(empty, *confirm(empty), max_visits=10)
    assert error.value.code == "no_moves"
