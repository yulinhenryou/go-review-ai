import json

from src.katago_client import CandidateMove, MockEngineClient, PositionAnalysis, PositionInput
from src.main import build_review_report_for_sgf, build_structured_review_for_game, build_structured_review_for_sgf
from src.sgf_parser import parse_sgf
from src.user_facing_labels import severity_label


def test_build_review_result_from_pipeline_data() -> None:
    review = build_structured_review_for_sgf(
        "samples/sample_game.sgf",
        engine=MockEngineClient(candidate_count=3),
        loss_threshold=1.0,
        limit=3,
    )
    payload = review.to_dict()

    assert review.schema_version == "2.0"
    assert payload["game_summary"]["board_size"] == 19
    assert payload["game_summary"]["players"]["black"] == "Black Player"
    assert payload["game_summary"]["moves_analyzed"] == 4
    assert payload["game_summary"]["mistakes_reviewed"] == 3

    assert payload["current_position"]["next_player"] == "B"
    assert payload["current_position"]["best_move"] == {"sgf": "jj", "display": "K10"}
    assert payload["current_position"]["score_estimate"] == 0.9
    assert payload["current_position"]["winrate"] == 0.53

    assert len(payload["timeline"]) == 4
    assert payload["timeline"][0] == {
        "move_number": 1,
        "color": "B",
        "played_move": {"sgf": "pd", "display": "Q16"},
        "best_move": {"sgf": "qd", "display": "R16"},
        "score_loss": 1.4,
        "winrate_delta": -0.06,
        "score_before": 1.8,
        "score_after": 0.4,
        "winrate_before": 0.54,
        "winrate_after": 0.48,
        "category": "local_overplay",
        "category_label": "局部用力过猛",
        "severity": "inaccuracy",
        "severity_label": "可商榷",
        "is_mistake": True,
    }

    assert [item["move_number"] for item in payload["selected_mistakes"]] == [3, 1, 2]
    assert payload["selected_mistakes"][0]["recommended_move"] == {
        "sgf": "cn",
        "display": "C6",
    }
    assert payload["selected_mistakes"][0]["score_loss"] == 1.8
    assert payload["selected_mistakes"][0]["estimated_loss"] == 1.8
    assert payload["selected_mistakes"][0]["winrate_delta"] == -0.08
    assert payload["selected_mistakes"][0]["category_label"] == "暂难归类"
    assert payload["selected_mistakes"][0]["severity_label"] == "问题手"

    assert payload["classifications"]["totals"] == [
        {"category": "local_overplay", "label": "局部用力过猛", "count": 1},
        {"category": "unclear", "label": "暂难归类", "count": 2},
    ]
    assert payload["review"]["mistakes_above_threshold"][0]["move_number"] == 3
    assert [item["move_number"] for item in payload["review"]["mistakes_above_threshold"]] == [3, 1, 2, 4]
    assert payload["review"]["classification_totals"] == [
        {"category": "local_overplay", "label": "局部用力过猛", "count": 1},
        {"category": "unclear", "label": "暂难归类", "count": 3},
    ]
    assert payload["review"]["training_suggestions"][0]["category"] == "unclear"

    assert payload["explanations"][0]["title"] == "Move 3 (暂难归类)"
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
    assert len(review.timeline) == 4
    assert "Top Mistakes" in report
    assert "Move 3: played qp (R4), best cn (C6), loss 1.80, 暂难归类" in report


def test_build_review_result_formats_pass_coordinate() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]KM[6.5]PB[A]PW[B];B[])")
    review = build_structured_review_for_game(
        game,
        engine=_PassPositionEngine(),
        loss_threshold=1.0,
        limit=3,
    )
    payload = review.to_dict()

    assert payload["selected_mistakes"] == []
    assert payload["timeline"][0]["played_move"] == {"sgf": None, "display": "pass"}
    assert payload["timeline"][0]["best_move"] == {"sgf": "qd", "display": "R16"}
    assert payload["current_position"]["best_move"] == {"sgf": "qd", "display": "R16"}


def test_severity_label_uses_chinese_user_facing_values() -> None:
    assert severity_label("inaccuracy") == "可商榷"
    assert severity_label("mistake") == "问题手"
    assert severity_label("major_mistake") == "明显失误"
    assert severity_label("blunder") == "大失误"


class _PassPositionEngine:
    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        return PositionAnalysis(
            best_move="qd",
            played_move=position.played_move,
            estimated_loss=0.0,
            score_estimate=1.6,
            winrate=0.54,
            played_score_estimate=1.6,
            played_winrate=0.54,
            top_candidates=(
                CandidateMove("qd", score_estimate=1.6, winrate=0.54),
                CandidateMove("dp", score_estimate=1.3, winrate=0.52),
                CandidateMove("pq", score_estimate=0.9, winrate=0.51),
            ),
            pv_summary="B qd -> W dp -> B pq",
        )
