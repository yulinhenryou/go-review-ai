from pathlib import Path

from src.sgf_parser import parse_sgf, parse_sgf_file


def test_parse_sgf_file_extracts_metadata_and_main_line_moves() -> None:
    game = parse_sgf_file(Path("samples/sample_game.sgf"))

    assert game.board_size == 19
    assert game.komi == 6.5
    assert game.black_player == "Black Player"
    assert game.white_player == "White Player"
    assert game.result == "W+R"

    # Parser should only follow the first branch after W[dd].
    assert [(m.color, m.point) for m in game.moves] == [
        ("B", "pd"),
        ("W", "dd"),
        ("B", "qp"),
        ("W", "dc"),
    ]


def test_parse_sgf_supports_missing_optional_properties() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19];B[aa];W[];B[cc])")

    assert game.board_size == 19
    assert game.rules is None
    assert game.missing_fields == ("rules", "komi")
    assert game.komi is None
    assert game.black_player is None
    assert game.white_player is None
    assert game.result is None
    assert [(m.color, m.point) for m in game.moves] == [
        ("B", "aa"),
        ("W", None),
        ("B", "cc"),
    ]


def test_parse_sgf_requires_board_size() -> None:
    try:
        parse_sgf("(;FF[4]GM[1];B[aa])")
    except ValueError as exc:
        assert "SZ" in str(exc)
    else:
        raise AssertionError("Expected ValueError when SZ is missing")


def test_validation_prints_metadata_and_move_count(capsys) -> None:
    game = parse_sgf_file("samples/sample_game.sgf")

    print(f"Board size: {game.board_size}")
    print(f"Komi: {game.komi}")
    print(f"Black: {game.black_player}")
    print(f"White: {game.white_player}")
    print(f"Result: {game.result}")
    print(f"Move count: {len(game.moves)}")

    out = capsys.readouterr().out
    assert "Board size: 19" in out
    assert "Move count: 4" in out
