from src.analyzer import analyze_sgf_file
from src.katago_client import MockEngineClient
from src.mistake_selector import print_mistake_summary, select_top_mistakes


def test_select_top_mistakes_applies_threshold() -> None:
    results = analyze_sgf_file("samples/sample_game.sgf", MockEngineClient(candidate_count=3))

    mistakes = select_top_mistakes(results, loss_threshold=1.3)

    assert [m.move_number for m in mistakes] == [3, 1]
    assert [m.estimated_loss for m in mistakes] == [1.8, 1.4]


def test_select_top_mistakes_ranks_by_loss_and_limits_to_top_three(capsys) -> None:
    results = analyze_sgf_file("samples/sample_game.sgf", MockEngineClient(candidate_count=3))

    mistakes = select_top_mistakes(results, loss_threshold=1.0, limit=3)

    assert [m.move_number for m in mistakes] == [3, 1, 2]
    assert [m.played_move for m in mistakes] == ["qp", "pd", "dd"]
    assert [m.recommended_move for m in mistakes] == ["cn", "qd", "dq"]
    assert [m.estimated_loss for m in mistakes] == [1.8, 1.4, 1.2]

    print_mistake_summary(mistakes)
    out = capsys.readouterr().out

    assert "Move 3: played=qp recommended=cn loss=1.80" in out
    assert "Move 1: played=pd recommended=qd loss=1.40" in out
    assert "Move 2: played=dd recommended=dq loss=1.20" in out
