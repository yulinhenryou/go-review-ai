from src.analyzer import analyze_game_state, analyze_sgf_file, print_move_summaries
from src.sgf_parser import parse_sgf_file
from src.katago_client import MockEngineClient


def test_move_by_move_pipeline_with_mock_engine(capsys) -> None:
    engine = MockEngineClient(candidate_count=3)

    results = analyze_sgf_file("samples/sample_game.sgf", engine)

    assert len(results) == 4

    # Position-like inputs should be built before each played move.
    assert results[0].position_input.moves == ()
    assert results[1].position_input.moves == (("B", "pd"),)
    assert results[2].position_input.moves == (("B", "pd"), ("W", "dd"))

    # Structured per-move analysis fields.
    assert results[0].move_number == 1
    assert results[0].played_move == "pd"
    assert results[0].recommended_move == "qd"
    assert results[0].estimated_loss == 1.4

    assert results[1].move_number == 2
    assert results[1].played_move == "dd"
    assert results[1].recommended_move == "dq"
    assert results[1].estimated_loss == 1.2

    print_move_summaries(results)
    out = capsys.readouterr().out

    assert "Move 1: played=pd recommended=qd loss=1.40" in out
    assert "Move 2: played=dd recommended=dq loss=1.20" in out
    assert "Move 3: played=qp recommended=cn loss=1.80" in out
    assert "Move 4: played=dc recommended=dq loss=1.20" in out


def test_analyze_game_state_includes_current_position() -> None:
    engine = MockEngineClient(candidate_count=3)
    game = parse_sgf_file("samples/sample_game.sgf")

    analysis = analyze_game_state(game, engine)

    assert len(analysis.move_results) == 4
    assert analysis.current_position_input.to_play == "B"
    assert analysis.current_position.best_move == "jj"
    assert analysis.current_position.score_estimate == 0.9
