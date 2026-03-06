import json

from src.analyzer import MoveAnalysisResult, analyze_sgf_file
from src.classifier import ClassifiedMistake, classify_selected_mistakes
from src.katago_client import CandidateMove, MockEngineClient, PositionAnalysis, PositionInput
from src.main import build_review_report_for_sgf, build_structured_review_for_sgf
from src.mistake_selector import select_top_mistakes
from src.review_result import build_review_result, review_result_to_dict
from src.sgf_parser import parse_sgf, parse_sgf_file


def test_build_review_result_from_pipeline_data() -> None:
    game = parse_sgf_file("samples/sample_game.sgf")
    results = analyze_sgf_file("samples/sample_game.sgf", MockEngineClient(candidate_count=3))
    selected = select_top_mistakes(results, loss_threshold=1.0, limit=3)
    classified = classify_selected_mistakes(selected, results)

    review = build_review_result(game, classified, results)
    payload = review_result_to_dict(review)

    assert review.schema_version == "1.0"
    assert payload["game_summary"]["board_size"] == 19
    assert payload["game_summary"]["players"]["black"] == "Black Player"
    assert payload["game_summary"]["moves_analyzed"] == 4
    assert payload["game_summary"]["mistakes_reviewed"] == 3

    assert [item["move_number"] for item in payload["selected_mistakes"]] == [3, 1, 2]
    assert payload["selected_mistakes"][0]["played_move"] == {"sgf": "qp", "display": "R4"}
    assert payload["selected_mistakes"][0]["recommended_move"] == {
        "sgf": "cn",
        "display": "C6",
    }
    assert payload["selected_mistakes"][0]["top_candidates"][0]["move"] == {
        "sgf": "cn",
        "display": "C6",
    }

    assert payload["classifications"]["by_move"][0]["category"] == "unclear"
    assert payload["classifications"]["totals"] == [
        {"category": "local_overplay", "label": "Local overplay", "count": 1},
        {"category": "unclear", "label": "Unclear classification", "count": 2},
    ]

    assert payload["explanations"][0]["title"] == "Move 3 (Unclear classification)"
    assert "KataGo prefers C6" in payload["explanations"][0]["summary"]
    assert payload["training_suggestions"][0]["suggestion"] == (
        "Recheck this position manually because the pattern is not conclusive."
    )

    json.dumps(payload)


def test_structured_review_builder_in_main_and_text_report_still_works() -> None:
    review = build_structured_review_for_sgf(
        "samples/sample_game.sgf",
        engine=MockEngineClient(candidate_count=3),
        loss_threshold=1.0,
        limit=3,
    )
    report = build_review_report_for_sgf(
        "samples/sample_game.sgf",
        engine=MockEngineClient(candidate_count=3),
        loss_threshold=1.0,
        limit=3,
    )

    assert review.game_summary.moves_analyzed == 4
    assert len(review.selected_mistakes) == 3
    assert "Top Mistakes" in report
    assert "Move 3: played qp (R4), best cn (C6), loss 1.80" in report


def test_build_review_result_formats_pass_coordinate() -> None:
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
    results = [_make_result_for_pass_move()]

    review = build_review_result(game, mistakes, results)
    payload = review.to_dict()

    assert payload["selected_mistakes"][0]["played_move"] == {"sgf": None, "display": "pass"}
    assert payload["selected_mistakes"][0]["recommended_move"] == {"sgf": "qd", "display": "R16"}


def _make_result_for_pass_move() -> MoveAnalysisResult:
    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play="B",
        moves=tuple(),
        played_move=None,
    )
    analysis = PositionAnalysis(
        best_move="qd",
        played_move=None,
        estimated_loss=1.1,
        top_candidates=(
            CandidateMove("qd", score_estimate=1.6, winrate=0.54),
            CandidateMove("dp", score_estimate=1.3, winrate=0.52),
            CandidateMove("pq", score_estimate=0.9, winrate=0.51),
        ),
        pv_summary="B qd -> W dp -> B pq",
    )
    return MoveAnalysisResult(
        move_number=1,
        color="B",
        played_move=None,
        recommended_move="qd",
        estimated_loss=1.1,
        position_input=position,
        engine_analysis=analysis,
    )
