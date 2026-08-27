from src.analyzer import analyze_sgf_file
from tests.mock_engine import MockEngineClient
from src.mistake_selector import (
    print_mistake_summary,
    select_mistakes_above_threshold,
    select_top_mistakes,
)


def test_select_mistakes_above_threshold_returns_all_qualifying_moves() -> None:
    results = analyze_sgf_file("samples/sample_game.sgf", MockEngineClient(candidate_count=3))

    mistakes = select_mistakes_above_threshold(results, loss_threshold=1.0)

    assert [m.move_number for m in mistakes] == [3, 1, 2, 4]
    assert [m.score_loss for m in mistakes] == [1.8, 1.4, 1.2, 1.2]
    assert [m.winrate_delta for m in mistakes] == [-0.08, -0.06, -0.05, -0.05]
    assert [m.severity for m in mistakes] == [
        "mistake",
        "inaccuracy",
        "inaccuracy",
        "inaccuracy",
    ]


def test_select_top_mistakes_applies_threshold() -> None:
    results = analyze_sgf_file("samples/sample_game.sgf", MockEngineClient(candidate_count=3))

    mistakes = select_top_mistakes(results, loss_threshold=1.3)

    assert [m.move_number for m in mistakes] == [3, 1]
    assert [m.score_loss for m in mistakes] == [1.8, 1.4]


def test_select_top_mistakes_ranks_by_loss_and_limits_to_top_three(capsys) -> None:
    results = analyze_sgf_file("samples/sample_game.sgf", MockEngineClient(candidate_count=3))

    mistakes = select_top_mistakes(results, loss_threshold=1.0, limit=3)

    assert [m.move_number for m in mistakes] == [3, 1, 2]
    assert [m.played_move for m in mistakes] == ["qp", "pd", "dd"]
    assert [m.recommended_move for m in mistakes] == ["cn", "qd", "dq"]
    assert [m.score_loss for m in mistakes] == [1.8, 1.4, 1.2]

    print_mistake_summary(mistakes)
    out = capsys.readouterr().out

    assert "Move 3: played=qp recommended=cn loss=1.80 winrate_delta=-0.08 severity=mistake" in out
    assert "Move 1: played=pd recommended=qd loss=1.40 winrate_delta=-0.06 severity=inaccuracy" in out
    assert "Move 2: played=dd recommended=dq loss=1.20 winrate_delta=-0.05 severity=inaccuracy" in out
