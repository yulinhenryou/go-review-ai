from src.analyzer import analyze_sgf_file
from src.classifier import ClassifiedMistake, classify_selected_mistakes
from src.katago_client import MockEngineClient
from src.main import print_sample_report
from src.mistake_selector import select_top_mistakes
from src.report_writer import generate_review_report
from src.sgf_parser import parse_sgf, parse_sgf_file


def test_generate_review_report_from_pipeline_data() -> None:
    game = parse_sgf_file("samples/sample_game.sgf")
    results = analyze_sgf_file("samples/sample_game.sgf", MockEngineClient(candidate_count=3))
    selected = select_top_mistakes(results, loss_threshold=1.0, limit=3)
    classified = classify_selected_mistakes(selected, results)

    report = generate_review_report(game, classified)

    assert "Game Summary" in report
    assert "- Board: 19x19" in report
    assert "- Players: Black Player (B) vs White Player (W)" in report
    assert "- Moves analyzed: 4" in report
    assert "Top Mistakes" in report
    assert "1. Move 3: played qp (R4), best cn (C6), loss 1.80" in report
    assert "2. Move 1: played pd (Q16), best qd (R16), loss 1.40" in report
    assert "3. Move 2: played dd (D16), best dq (D3), loss 1.20" in report
    assert "Mistake Explanations" in report
    assert "KataGo prefers" in report
    assert "Why this matters:" in report
    assert "Final Training Suggestions" in report


def test_generate_review_report_unclear_classification_is_explicit() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]KM[6.5]PB[A]PW[B];B[pd])")
    mistakes = [
        ClassifiedMistake(
            move_number=1,
            played_move="pd",
            recommended_move="qd",
            estimated_loss=0.8,
            category="unclear",
        )
    ]

    report = generate_review_report(game, mistakes)

    assert "Move 1 (Unclear classification)" in report
    assert "Engine signals are mixed, so this pattern is not yet clear." in report


def test_print_sample_report_for_sample_pipeline(capsys) -> None:
    print_sample_report("samples/sample_game.sgf", engine=MockEngineClient(candidate_count=3))
    out = capsys.readouterr().out

    assert "Game Summary" in out
    assert "Top Mistakes" in out
    assert "Mistake Explanations" in out
    assert "Final Training Suggestions" in out
    assert "Move 3: played qp (R4), best cn (C6), loss 1.80" in out


def test_generate_review_report_formats_pass_move() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]KM[6.5]PB[A]PW[B];B[])")
    mistakes = [
        ClassifiedMistake(
            move_number=1,
            played_move=None,
            recommended_move="qd",
            estimated_loss=1.1,
            category="defensive_overreaction",
        )
    ]

    report = generate_review_report(game, mistakes)

    assert "played pass" in report
    assert "best qd (R16)" in report
