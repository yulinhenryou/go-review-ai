from src.katago_client import MockEngineClient, PositionInput


def test_mock_client_returns_structured_analysis() -> None:
    client = MockEngineClient()

    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play="B",
        moves=(("B", "pd"), ("W", "dd"), ("B", "qp")),
        played_move="dc",
    )

    analysis = client.analyze_position(position)

    assert analysis.best_move == "qd"
    assert analysis.played_move == "dc"
    assert analysis.estimated_loss >= 0.0
    assert len(analysis.top_candidates) == 3
    assert analysis.top_candidates[0].move == "qd"
    assert "B" in analysis.pv_summary


def test_mock_client_accepts_best_move_as_zero_loss() -> None:
    client = MockEngineClient()

    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play="W",
        moves=(("B", "pd"),),
        played_move="dq",
    )

    analysis = client.analyze_position(position)

    assert analysis.best_move == "dq"
    assert analysis.estimated_loss == 0.0


def test_mock_client_rejects_invalid_to_play() -> None:
    client = MockEngineClient()

    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play="X",  # type: ignore[arg-type]
        moves=(),
        played_move=None,
    )

    try:
        client.analyze_position(position)
    except ValueError as exc:
        assert "to_play" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid to_play")


def test_mock_client_analyzes_position_like_input() -> None:
    client = MockEngineClient()

    analysis = client.analyze_position(
        PositionInput(
            board_size=13,
            komi=0.5,
            to_play="B",
            moves=(("B", "dd"), ("W", "jj")),
            played_move="kk",
        )
    )

    assert isinstance(analysis.best_move, str)
    assert len(analysis.top_candidates) == 3
    assert analysis.pv_summary
    assert analysis.estimated_loss > 0.0
