"""The `weiqi_core` binding: rule cases ported from the prototype's
tests/test_game_input.py (MIGRATION G02), error codes, and the copy-out
boundary. Rule behavior itself is tested in Rust; these tests check that the
binding exposes it faithfully.
"""

from typing import TYPE_CHECKING

import pytest
import weiqi_core as core

if TYPE_CHECKING:
    from weiqi_core import Move, Point


def sgf(text: str) -> Point:
    return (ord(text[0]) - ord("a"), ord(text[1]) - ord("a"))


def game(rules: str = "japanese", komi: float = 6.5) -> core.Game:
    return core.Game(19, 19, core.Rules.from_name(rules), komi)


def play_all(g: core.Game, points: list[str]) -> None:
    for point in points:
        g.play("pass" if point == "pass" else sgf(point))


# The prototype's KO_MOVES with its ss tenuki: Black takes the ko at cb last.
KO_MOVES = ["ba", "bb", "ab", "ca", "bc", "cc", "ss", "db", "cb"]


@pytest.mark.parametrize("rules", ["japanese", "chinese"])
def test_simple_ko_and_legal_recapture_after_intervening_moves(rules: str) -> None:
    g = game(rules)
    play_all(g, KO_MOVES)
    assert g.position().ko_ban == sgf("bb")
    with pytest.raises(core.IllegalMoveError) as error:
        g.play(sgf("bb"))
    assert error.value.code == "ko_violation"
    assert g.move_count == len(KO_MOVES)
    play_all(g, ["rr", "qq"])
    effect = g.play(sgf("bb"))
    assert effect.captured == [sgf("cb")]
    assert g.position().cells[sgf("bb")[1] * 19 + sgf("bb")[0]] == "W"


@pytest.mark.parametrize("rules", ["japanese", "chinese"])
@pytest.mark.parametrize(
    "points", [["ba", "ss", "ab", "aa"], ["ca", "aa", "bb", "ab", "ac", "ba"]], ids=["one", "multi"]
)
def test_single_and_multi_stone_suicide_are_rejected(rules: str, points: list[str]) -> None:
    g = game(rules)
    play_all(g, points[:-1])
    before = g.position().situation_hash
    with pytest.raises(core.IllegalMoveError) as error:
        g.play(sgf(points[-1]))
    assert error.value.code == "suicide"
    assert g.position().situation_hash == before


def test_multi_stone_suicide_is_applied_under_tromp_taylor() -> None:
    g = game("tromp-taylor", 7.5)
    play_all(g, ["ca", "aa", "bb", "ab", "ac"])
    effect = g.play(sgf("ba"))
    assert sorted(effect.suicided) == sorted([sgf("aa"), sgf("ab"), sgf("ba")])
    assert g.position().captures.white == 3


def test_pass_switches_player_and_two_passes_do_not_end_the_game() -> None:
    # Changed expectation (M1): the prototype rejected a move after two
    # passes; the core only counts passes and the product layer decides.
    g = game()
    play_all(g, ["aa", "pass", "pass"])
    position = g.position()
    assert position.to_play == "W"
    assert position.consecutive_passes == 2
    g.play(sgf("bb"))
    assert g.position().consecutive_passes == 0
    assert g.moves() == [("B", sgf("aa")), ("W", "pass"), ("B", "pass"), ("W", sgf("bb"))]


def test_out_of_turn_is_rejected_strictly_and_reported_in_record_mode() -> None:
    g = game()
    g.play(sgf("aa"))
    with pytest.raises(core.IllegalMoveError) as error:
        g.play_as("B", sgf("bb"))
    assert error.value.code == "out_of_turn"
    effect = g.play_as("B", sgf("bb"), "record")
    assert effect.violations == ["out_of_turn"]
    assert g.to_play == "W"


@pytest.mark.parametrize(
    ("move", "error_type", "code"),
    [
        ((19, 0), core.IllegalMoveError, "off_board"),
        ((0, 19), core.IllegalMoveError, "off_board"),
        ((-1, 0), core.IllegalMoveError, "off_board"),
        ((2**70, 0), core.IllegalMoveError, "off_board"),
        ("tt", core.CoreError, "malformed_move"),
        ("", core.CoreError, "malformed_move"),
        ("PASS", core.CoreError, "malformed_move"),
        ((1,), core.CoreError, "malformed_move"),
        ((1, 2, 3), core.CoreError, "malformed_move"),
        (1, core.CoreError, "malformed_move"),
        (None, core.CoreError, "malformed_move"),
    ],
)
def test_coordinate_validation(move: object, error_type: type[core.CoreError], code: str) -> None:
    g = game()
    with pytest.raises(error_type) as error:
        g.play(move)  # type: ignore[arg-type]
    assert error.value.code == code
    assert g.move_count == 0


def test_occupied_point_is_rejected_in_both_modes() -> None:
    g = game()
    g.play(sgf("aa"))
    for mode in ("strict", "record"):
        with pytest.raises(core.IllegalMoveError) as error:
            g.play_as("W", sgf("aa"), mode)
        assert error.value.code == "occupied"


@pytest.mark.parametrize("komi", [float("nan"), float("inf"), -151, 151, 0.25])
def test_komi_validation(komi: float) -> None:
    with pytest.raises(core.CoreError) as error:
        game(komi=komi)
    assert error.value.code == "invalid_komi"


def test_komi_must_be_a_number() -> None:
    with pytest.raises(TypeError):
        game(komi="6.5")  # type: ignore[arg-type]


@pytest.mark.parametrize(("width", "height"), [(0, 19), (19, 26), (-1, 5), (300, 300)])
def test_unsupported_board_sizes(width: int, height: int) -> None:
    with pytest.raises(core.CoreError) as error:
        core.Game(width, height, core.Rules.from_name("chinese"), 7.5)
    assert error.value.code == "unsupported_size"


@pytest.mark.parametrize(
    ("value", "code"),
    [("X", "malformed_color"), ("b", "malformed_color")],
)
def test_colors_are_b_or_w(value: str, code: str) -> None:
    with pytest.raises(core.CoreError) as error:
        game().play_as(value, sgf("aa"))  # type: ignore[arg-type]
    assert error.value.code == code


def test_unknown_rules_and_mode() -> None:
    with pytest.raises(core.CoreError) as error:
        core.Rules.from_name("ing")
    assert error.value.code == "unknown_rules"
    with pytest.raises(core.CoreError) as error:
        game().play_as("B", sgf("aa"), "lenient")  # type: ignore[arg-type]
    assert error.value.code == "malformed_mode"


def test_setup_errors_carry_core_codes() -> None:
    rules = core.Rules.from_name("japanese")
    with pytest.raises(core.CoreError) as error:
        core.Game(9, 9, rules, 0.5, core.Setup(black=[(9, 0)]))
    assert error.value.code == "setup_off_board"
    with pytest.raises(core.CoreError) as error:
        core.Game(9, 9, rules, 0.5, core.Setup(black=[(0, 0)], white=[(0, 0)]))
    assert error.value.code == "setup_conflict"


def test_snapshots_are_copies_and_frozen() -> None:
    g = game()
    position = g.position()
    g.play(sgf("dd"))
    assert position.cells[3 * 19 + 3] is None
    assert g.position().cells[3 * 19 + 3] == "B"

    cells = position.cells
    cells[0] = "W"
    assert position.cells[0] is None

    with pytest.raises(AttributeError):
        position.to_play = "W"  # type: ignore[misc]

    black: list[Point] = [(2, 2)]
    setup = core.Setup(black=black, to_play="W")
    black.clear()
    assert setup.black == [(2, 2)]


def test_undo_restores_every_position() -> None:
    g = game()
    hashes = [g.position().situation_hash]
    for point in KO_MOVES:
        g.play(sgf(point))
        hashes.append(g.position().situation_hash)
    undone: list[Move] = []
    while (last := g.undo()) is not None:
        undone.append(last[1])
        hashes.pop()
        assert g.position().situation_hash == hashes[-1]
    assert undone == [sgf(p) for p in reversed(KO_MOVES)]
    assert g.undo() is None


def test_a_pass_changes_the_situation_hash_but_not_the_stones_hash() -> None:
    g = game()
    g.play(sgf("dd"))
    before = g.position()
    g.play("pass")
    after = g.position()
    assert 0 <= after.stones_hash < 2**128
    assert after.stones_hash == before.stones_hash
    assert after.situation_hash != before.situation_hash


def test_sgf_pipeline_and_errors() -> None:
    collection = core.parse_sgf(b"(;FF[4]GM[1]SZ[9]RU[Japanese]KM[6.5]PB[A\\]B];B[ee];W[tt])")
    assert collection.encoding == "UTF-8"
    [tree] = collection.games
    assert len(tree) == 3
    record = core.extract(tree)
    assert record.info.black_player == "A]B"
    assert record.rules == core.Rules.from_name("japanese")
    assert record.komi == 6.5
    assert record.moves == [("B", (4, 4)), ("W", "pass")]
    assert [w.code for w in record.warnings] == ["tt_pass"]
    replay = record.replay(core.Rules.from_name("japanese"), 6.5)
    assert len(replay.positions) == 3
    assert core.parse_sgf(tree.to_sgf().encode()).games[0].to_sgf() == tree.to_sgf()

    with pytest.raises(core.SgfError) as sgf_error:
        core.parse_sgf(b"hello")
    assert (sgf_error.value.code, sgf_error.value.offset) == ("no_game", 5)

    [tree] = core.parse_sgf(b"(;SZ[9];B[aa]W[bb])").games
    with pytest.raises(core.ExtractError) as extract_error:
        core.extract(tree)
    assert extract_error.value.code == "two_moves_in_node"

    record = core.extract(core.parse_sgf(b"(;SZ[9];B[aa];W[bb];B[bb])").games[0])
    with pytest.raises(core.ReplayError) as replay_error:
        record.replay(core.Rules.from_name("chinese"), 7.5)
    assert (replay_error.value.code, replay_error.value.move_number) == ("occupied", 3)


def test_exception_hierarchy() -> None:
    for error_type in (core.IllegalMoveError, core.SgfError, core.ExtractError, core.ReplayError):
        assert issubclass(error_type, core.CoreError)
    assert issubclass(core.CoreError, ValueError)


# GTP vertices, the notation KataGo uses. The 19x19 pairs are the
# prototype's test_coordinate_mapping (MIGRATION E08); "I" is never a column.
@pytest.mark.parametrize(
    ("vertex", "point"),
    [("A19", (0, 0)), ("T1", (18, 18)), ("Q16", (15, 3)), ("H19", (7, 0)), ("J19", (8, 0))],
)
def test_gtp_vertices_round_trip(vertex: str, point: Point) -> None:
    assert core.to_gtp(point, 19, 19) == vertex
    assert core.from_gtp(vertex, 19, 19) == point
    assert core.from_gtp(vertex.lower(), 19, 19) == point


def test_gtp_pass_and_rectangular_boards() -> None:
    assert core.to_gtp("pass", 19, 19) == "pass"
    assert core.from_gtp("PASS", 9, 9) == "pass"
    # Rows count from the bottom of the board's own height.
    assert core.to_gtp((2, 0), 5, 3) == "C3"
    assert core.from_gtp("C1", 5, 3) == (2, 2)


@pytest.mark.parametrize(
    ("vertex", "code"),
    [
        ("I4", "malformed_coordinate"),
        ("Q0", "malformed_coordinate"),
        ("Q016", "malformed_coordinate"),
        ("", "malformed_coordinate"),
        ("Q20", "coordinate_out_of_range"),
        ("Z19", "coordinate_out_of_range"),
    ],
)
def test_gtp_rejects_bad_vertices(vertex: str, code: str) -> None:
    with pytest.raises(core.CoreError) as error:
        core.from_gtp(vertex, 19, 19)
    assert error.value.code == code


def test_gtp_formatting_checks_the_board() -> None:
    with pytest.raises(core.IllegalMoveError) as off_board:
        core.to_gtp((9, 0), 9, 9)
    assert off_board.value.code == "off_board"
    with pytest.raises(core.CoreError) as size:
        core.to_gtp("pass", 26, 26)
    assert size.value.code == "unsupported_size"
