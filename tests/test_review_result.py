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
    assert payload["current_position"]["short_explanation"] == (
        "现在轮到黑棋。KataGo建议走K10，目差预计为0.9，胜率约53%。"
    )
    assert payload["key_points"]["turning_points"] == [
        {
            "move_number": 3,
            "color": "B",
            "score_loss": 1.8,
            "winrate_delta": -0.08,
            "severity": "mistake",
            "severity_label": "问题手",
            "phase": "中盘",
            "summary": "第3手是中盘阶段的重要转折点，这一手让局面损失1.80目，胜率波动-8%。",
        },
        {
            "move_number": 1,
            "color": "B",
            "score_loss": 1.4,
            "winrate_delta": -0.06,
            "severity": "inaccuracy",
            "severity_label": "可商榷",
            "phase": "布局",
            "summary": "第1手是布局阶段的重要转折点，这一手让局面损失1.40目，胜率波动-6%。",
        },
        {
            "move_number": 2,
            "color": "W",
            "score_loss": 1.2,
            "winrate_delta": -0.05,
            "severity": "inaccuracy",
            "severity_label": "可商榷",
            "phase": "中盘",
            "summary": "第2手是中盘阶段的重要转折点，这一手让局面损失1.20目，胜率波动-5%。",
        },
    ]
    assert payload["key_points"]["plan_breaks"] == []
    assert payload["key_points"]["phase_summary"] == {
        "opening_loss": 1.4,
        "middle_game_loss": 3.0,
        "endgame_loss": 1.2,
        "biggest_problem_phase": "中盘",
        "main_issue": "fighting",
        "summary": "全局看，损失主要集中在中盘，主因是接触战。",
    }
    assert payload["key_points"]["review_summary"] == {
        "opening": "布局阶段大体平稳，但有零星可惜之处，累计损失约1.40目。",
        "middle_game": "中盘阶段问题比较集中，累计损失约3.00目。",
        "endgame": "官子阶段大体平稳，但有零星可惜之处，累计损失约1.20目。",
        "main_turning_points": [
            "第3手：第3手是中盘阶段的重要转折点，这一手让局面损失1.80目，胜率波动-8%。",
            "第1手：第1手是布局阶段的重要转折点，这一手让局面损失1.40目，胜率波动-6%。",
            "第2手：第2手是中盘阶段的重要转折点，这一手让局面损失1.20目，胜率波动-5%。",
        ],
        "loss_cause": "fighting",
        "summary": "这盘棋的胜负手主要出现在中盘，核心问题是接触战。全局最值得回看的关键点共有3处。",
    }

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

    assert payload["explanations"][0]["title"] == "第3手（暂难归类）"
    assert "这是本局关键处之一。中盘第3手" in payload["explanations"][0]["summary"]
    assert payload["training_suggestions"][0]["suggestion"] == (
        "这类棋形先不要急着下结论，复盘时把实战和推荐变化摆一遍再判断。"
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
    assert len(review.key_points.turning_points) == 3
    assert len(review.timeline) == 4
    assert "整局总结" in report
    assert "第3手：实战qp（R4），推荐cn（C6），损失1.80目，暂难归类" in report


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
    assert payload["key_points"]["turning_points"][0]["move_number"] == 1
    assert payload["current_position"]["short_explanation"] == (
        "现在轮到白棋。KataGo建议走R16，目差预计为1.6，胜率约54%。"
    )


def test_current_position_recommendation_exists_even_without_selected_mistakes() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]KM[6.5]PB[A]PW[B];B[pd];W[dd])")

    review = build_structured_review_for_game(
        game,
        engine=_OpeningNoMistakesEngine(),
        loss_threshold=1.0,
        limit=3,
    )
    payload = review.to_dict()

    assert payload["selected_mistakes"] == []
    assert payload["game_summary"]["mistakes_reviewed"] == 0
    assert payload["key_points"]["plan_breaks"] == []
    assert payload["current_position"] == {
        "next_player": "B",
        "best_move": {"sgf": "pq", "display": "Q3"},
        "top_candidates": [
            {
                "move": {"sgf": "pq", "display": "Q3"},
                "score_estimate": 0.4,
                "winrate": 0.51,
            },
            {
                "move": {"sgf": "dp", "display": "D4"},
                "score_estimate": 0.3,
                "winrate": 0.5,
            },
            {
                "move": {"sgf": "cq", "display": "C3"},
                "score_estimate": 0.2,
                "winrate": 0.49,
            },
        ],
        "pv_summary": "B pq -> W dp -> B cq",
        "score_estimate": 0.4,
        "winrate": 0.51,
        "short_explanation": (
            "现在轮到黑棋。KataGo建议走Q3，目差预计为0.4，胜率约51%。"
        ),
    }


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


class _OpeningNoMistakesEngine:
    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        if len(position.moves) == 2 and position.played_move is None:
            return PositionAnalysis(
                best_move="pq",
                played_move=None,
                estimated_loss=0.0,
                score_estimate=0.4,
                winrate=0.51,
                played_score_estimate=0.4,
                played_winrate=0.51,
                top_candidates=(
                    CandidateMove("pq", score_estimate=0.4, winrate=0.51),
                    CandidateMove("dp", score_estimate=0.3, winrate=0.5),
                    CandidateMove("cq", score_estimate=0.2, winrate=0.49),
                ),
                pv_summary="B pq -> W dp -> B cq",
            )

        return PositionAnalysis(
            best_move=position.played_move or "pq",
            played_move=position.played_move,
            estimated_loss=0.0,
            score_estimate=0.1,
            winrate=0.5,
            played_score_estimate=0.1,
            played_winrate=0.5,
            top_candidates=(
                CandidateMove(position.played_move or "pq", score_estimate=0.1, winrate=0.5),
                CandidateMove("dp", score_estimate=0.0, winrate=0.49),
                CandidateMove("cq", score_estimate=-0.1, winrate=0.48),
            ),
            pv_summary="B pq -> W dp -> B cq",
        )
