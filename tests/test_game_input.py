from dataclasses import FrozenInstanceError, replace

import pytest

from app.models import GamePayload
from src.analyzer import analyze_game_state
from src.game import (
    MAX_SGF_BYTES, GameInputError, GameMove, GameRecord,
    input_preview, validate_game, validate_review_options,
)
from tests.mock_engine import MockEngineClient
from src.sgf_parser import parse_sgf, parse_sgf_bytes, parse_sgf_file


KO_MOVES = "ba bb ab ca bc cc ss db cb".split()


def make_game(points, *, rules="japanese", komi=6.5):
    return GameRecord(
        board_size=19, rules=rules, komi=komi, black_player=None, white_player=None,
        result=None, moves=tuple(GameMove("B" if i % 2 == 0 else "W", p) for i, p in enumerate(points)),
    )


@pytest.mark.parametrize("rules", ["japanese", "chinese"])
def test_sgf_and_manual_inputs_have_identical_records_and_every_position(rules):
    points = ["ba", "aa", "ab", None, "ss"]
    game = make_game(points, rules=rules)
    sgf = f"(;FF[4]GM[1]SZ[19]RU[{rules}]KM[6.5]" + "".join(
        f";{m.color}[{m.point or ''}]" for m in game.moves
    ) + ")"
    manual = GamePayload.model_validate({
        "board_size": 19, "rules": rules, "komi": 6.5,
        "moves": [{"color": m.color, "sgf": m.point} for m in game.moves],
    }).to_game_record()
    parsed = parse_sgf(sgf)
    assert parsed == manual == game
    assert validate_game(parsed) == validate_game(manual)
    assert ("W", "aa") not in validate_game(parsed)[3].stones
    assert validate_game(parsed)[3].stones == validate_game(parsed)[4].stones
    assert validate_game(parsed)[-1].next_player == "W"


@pytest.mark.parametrize("rules", ["japanese", "chinese"])
def test_simple_ko_and_legal_recapture_after_intervening_moves(rules):
    with pytest.raises(GameInputError) as error:
        validate_game(make_game(KO_MOVES + ["bb"], rules=rules))
    assert error.value.code == "ko_violation"
    assert error.value.move_number == 10
    snapshots = validate_game(make_game(KO_MOVES + ["rr", "qq", "bb"], rules=rules))
    assert ("W", "bb") in snapshots[-1].stones
    assert ("B", "cb") not in snapshots[-1].stones


@pytest.mark.parametrize("rules", ["japanese", "chinese"])
@pytest.mark.parametrize("points", [["ba", "ss", "ab", "aa"], ["ca", "aa", "bb", "ab", "ac", "ba"]])
def test_single_and_multi_stone_suicide_are_rejected(rules, points):
    with pytest.raises(GameInputError) as error:
        validate_game(make_game(points, rules=rules))
    assert error.value.code == "suicide"
    assert error.value.move_number == len(points)


def test_pass_switches_player_and_two_passes_do_not_invent_a_result():
    game = make_game(["aa", None, None])
    snapshots = validate_game(game)
    assert snapshots[-1].stones == snapshots[1].stones
    assert snapshots[-1].next_player == "W"
    assert game.record_status == "unfinished_or_unknown"
    assert game.result is None
    with pytest.raises(GameInputError, match="two consecutive passes"):
        validate_game(make_game(["aa", None, None, "bb"]))


def test_root_move_bom_and_escaped_utf8_metadata():
    data = b"\xef\xbb\xbf" + '(;FF[4]SZ[19]CA[UTF-8]RU[Chinese]KM[7.5]PB[A\\]B]PW[\u68cb\u624b]B[as];W[sa])'.encode()
    game = parse_sgf_bytes(data)
    assert game.black_player == "A]B"
    assert game.white_player == "\u68cb\u624b"
    assert game.moves == (GameMove("B", "as"), GameMove("W", "sa"))
    assert ("B", "as") in validate_game(game)[-1].stones


def test_first_variation_only_has_an_explicit_warning():
    game = parse_sgf("(;SZ[19]RU[Japanese]KM[6.5];B[aa](;W[bb])(;W[cc]))")
    assert game.moves[-1].point == "bb"
    assert input_preview(game)["warnings"] == ["first_variation_only"]


def test_missing_metadata_can_be_previewed_but_never_analyzed():
    game = parse_sgf("(;SZ[19];B[aa])")
    assert input_preview(game)["missing_fields"] == ["rules", "komi"]
    assert input_preview(game)["status"] == "needs_metadata"
    with pytest.raises(GameInputError) as error:
        validate_game(game)
    assert error.value.code == "missing_metadata"
    confirmed = parse_sgf("(;SZ[19];B[aa])", rules="chinese", komi=7.5)
    assert input_preview(confirmed)["status"] == "ready"
    recorded = parse_sgf("(;SZ[19]RU[Japanese]KM[0];B[aa])", rules="chinese", komi=7.5)
    assert recorded.rules == "japanese" and recorded.komi == 0


@pytest.mark.parametrize("sgf", [
    "junk (;SZ[19];B[aa])", "((;SZ[19];B[aa])", "(junk(;SZ[19];B[aa])",
    "(;SZ[19];B[aa]) junk", "(;SZ[19];B[aa])(;SZ[19];B[bb])",
    "(;SZ[19];B[aa]", "(;SZ[19];B[aa][bb])", "(;SZ[19];B[aa]B[bb])",
    "(;SZ[19];B[aa]W[bb])", "(;SZ[19]KM[6.5]KM[7.5];B[aa])", "(;SZ[19];B)",
    "(;SZ[19];B[tt])", "(;SZ[19];B[AA])", "(;SZ[19];B[\u00e9a])", "(;SZ[19];B[aaa])",
    "(;SZ[19]AB[aa];W[bb])", "(;SZ[19];B[aa];AW[bb])", "(;SZ[19];B[aa];AE[aa])",
    "(;SZ[19]PL[W];W[bb])", "(;SZ[19]HA[2];B[aa])", "(;SZ[19];B[aa]KO[])",
    "(;SZ[19]GM[2];B[aa])", "(;SZ[19]FF[3];B[aa])", "(;SZ[13];B[aa])",
    "(;SZ[19:19];B[aa])", "(;SZ[19]CA[GBK];B[aa])", "(;SZ[19]RU[AGA];B[aa])",
    "(;SZ[19]KM[NaN];B[aa])", "(;SZ[19]KM[Infinity];B[aa])", "(;SZ[19]KM[0.25];B[aa])",
    "(;SZ[19]KM[151];B[aa])", "(;SZ[19];B[aa];KM[7.5]W[bb])",
    "(;SZ[19];W[aa])", "(;SZ[19];B[aa];B[bb])", "(;SZ[19];B[aa];W[aa])", "(;SZ[19])",
])
def test_malformed_or_unsupported_sgf_is_rejected(sgf):
    with pytest.raises(GameInputError):
        parse_sgf(sgf)


def test_upload_byte_and_tree_node_limits(tmp_path):
    data = b"(;SZ[19];B[aa])" + b" " * MAX_SGF_BYTES
    with pytest.raises(GameInputError, match="1 MiB"):
        parse_sgf_bytes(data)
    path = tmp_path / "large.sgf"
    path.write_bytes(data)
    with pytest.raises(GameInputError, match="1 MiB"):
        parse_sgf_file(path)
    with pytest.raises(GameInputError, match="5000 nodes"):
        parse_sgf("(;SZ[19];B[aa]" + ";C[n]" * 5000 + ")")


def test_move_count_boundaries():
    points = [chr(97 + i % 19) + chr(97 + i // 19) for i in range(250)]
    game = make_game([move for point in points for move in (point, None)])
    assert len(validate_game(game)) == 501
    with pytest.raises(GameInputError, match="1-500"):
        validate_game(replace(game, moves=game.moves + (GameMove("B", "qs"),)))
    with pytest.raises(GameInputError, match="1-500"):
        validate_game(make_game([]))


@pytest.mark.parametrize("point", ["", "pass", "tt", "aa ", "AA", "\u00e9a", 1, True])
def test_manual_coordinate_validation_is_not_bypassed(point):
    with pytest.raises(GameInputError):
        validate_game(make_game([point]))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -151, 151, .25, True, "6.5"])
def test_komi_validation_is_shared(value):
    with pytest.raises(GameInputError) as error:
        validate_game(make_game(["aa"], komi=value))
    assert error.value.code == "invalid_komi"


@pytest.mark.parametrize("threshold,limit", [(float("nan"), 1), (float("inf"), 1), (-1, 1), (362, 1), (1, 0), (1, 501), (1, True), (True, 1)])
def test_review_option_limits(threshold, limit):
    with pytest.raises(GameInputError):
        validate_review_options(threshold, limit)


def test_records_are_immutable_and_pass_is_distinct_from_current_position():
    source_moves = [GameMove("B", None)]
    game = replace(make_game([None]), moves=source_moves)
    source_moves.clear()
    assert len(game.moves) == 1
    with pytest.raises(FrozenInstanceError):
        game.komi = 0
    analysis = analyze_game_state(game, MockEngineClient())
    played = analysis.move_results[0].position_input
    current = analysis.current_position_input
    assert played.played_move is None and current.played_move is None
    assert played.analysis_kind == "played_move"
    assert current.analysis_kind == "current_position"
    assert played.rules == current.rules == "japanese"
    assert analysis.move_results[0].estimated_loss > 0
    assert analysis.current_position.estimated_loss == 0
