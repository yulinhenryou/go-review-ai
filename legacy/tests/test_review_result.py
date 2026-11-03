from dataclasses import replace
import json

import pytest

from src.review_service import build_structured_review_for_game
from src.sgf_parser import parse_sgf
from tests.report_fixtures import FixedEvidenceEngine, game_with_moves


def review(losses, overrides=None, **options):
    return build_structured_review_for_game(game_with_moves(len(losses)), FixedEvidenceEngine(losses, overrides), **options)


def test_schema_three_separates_chronology_from_ranked_summary():
    result = review([3, 7, 6, 5, 4, 8])
    assert result.schema_version == "3.0"
    assert result.status == "complete"
    assert [item.move_number for item in result.selected_mistakes] == [6, 2, 3, 4, 5]
    assert [item.move_number for item in result.review.mistakes_above_threshold] == [1, 2, 3, 4, 5, 6]
    assert len(result.timeline) == 6
    assert result.method.loss_threshold == 3
    assert result.method.severe_threshold == 5
    assert result.method.top_limit == 5
    payload = result.to_dict()
    assert not {"key_points", "classifications", "explanations", "training_suggestions"} & payload.keys()
    assert not {"category", "teaching_label", "swing_direction", "winrate_delta"} & payload["timeline"][0].keys()
    json.dumps(payload, allow_nan=False)


def test_missing_score_is_partial_not_clean_and_current_values_can_still_be_used():
    result = review([None, 0])
    assert result.status == "partial"
    assert result.coverage.moves_evaluated == 1
    assert result.coverage.missing_move_numbers == (1,)
    assert result.timeline[0].is_mistake is None
    assert result.timeline[0].severity is None
    assert "报告不完整" in result.summary
    assert "未发现明显失误" not in result.summary
    assert result.current_position.best_move.display == "Q16"


def test_missing_winrate_keeps_point_loss_and_severity_without_fabricated_rate():
    result = review([6], {0: {"played_winrate": None}})
    assert result.status == "partial"
    assert result.coverage.moves_evaluated == 1
    assert result.coverage.moves_with_winrate == 0
    assert result.coverage.missing_winrate_move_numbers == (1,)
    item = result.selected_mistakes[0]
    assert item.score_loss == 6
    assert item.severity == "severe"
    assert item.winrate_delta_pp is None
    assert item.winrate_black_after is None
    assert "胜率变化不可用" in item.summary


def test_missing_current_evaluation_makes_report_partial():
    result = review([3], {1: {"score_estimate": None, "winrate": None, "best_move": None, "top_candidates": ()}})
    assert not result.coverage.current_position_evaluated
    assert result.status == "partial"
    assert result.current_position.best_move is None
    assert "不可用" in result.current_position.short_explanation


def test_terminal_root_values_without_candidates_do_not_invent_a_pass_recommendation():
    result = review([0], {1: {"best_move": None, "top_candidates": ()}})
    assert result.status == "complete"
    assert result.current_position.best_move is None
    assert result.current_position.pv_summary == ""
    assert "停一手" not in result.current_position.short_explanation


def test_pv_comes_only_from_its_recommendation_not_legacy_prose_or_other_candidates():
    result = review([3, 4])
    for item in result.selected_mistakes:
        assert item.pv[0].color == item.color
        assert item.pv[0].move == item.recommended_move.sgf
        assert "untrusted" not in item.pv_summary
        assert "A19" not in item.pv_summary
    no_pv = review([3], {0: {"top_candidates": ()}})
    assert no_pv.selected_mistakes[0].pv == ()
    assert no_pv.selected_mistakes[0].pv_summary == ""
    assert "missing_pv" in no_pv.warnings


def test_fixed_black_chart_and_moving_player_loss_agree_for_both_colors():
    for item in review([3, 4]).timeline:
        sign = 1 if item.color == "B" else -1
        assert item.score_black_before - item.score_black_after == pytest.approx(item.raw_score_loss * sign)
        assert item.winrate_delta_pp == pytest.approx(-20)
        assert item.winrate_black_after == (.4 if sign == 1 else .6)
        assert ("黑棋胜率" if sign == 1 else "白棋胜率") in item.summary


def test_pass_is_not_a_missing_move_and_result_metadata_is_not_inferred():
    game = parse_sgf("(;SZ[19]RU[Chinese]KM[7.5];B[])")
    result = build_structured_review_for_game(game, FixedEvidenceEngine([3]))
    assert result.selected_mistakes[0].played_move.sgf is None
    assert result.selected_mistakes[0].played_move.display == "停一手"
    assert result.game_summary.record_status == "unfinished_or_unknown"
    assert result.game_summary.result is None


def test_warning_provenance_and_negative_difference_survive_serialization():
    engine = FixedEvidenceEngine([-1])
    game = game_with_moves(1)
    from src.analyzer import analyze_game_state
    from src.review_result import build_review_result
    analysis = analyze_game_state(game, engine)
    first = analysis.move_results[0]
    evidence = replace(first.engine_analysis.evidence, warnings=("low_visits", "separate_search"))
    analysis.move_results[0] = replace(first, engine_analysis=replace(first.engine_analysis, evidence=evidence))
    result = build_review_result(game, analysis, 3, 5, 5)
    assert {"low_visits", "separate_search", "negative_difference_search_noise"} <= set(result.warnings)
    assert result.timeline[0].raw_score_loss == -1
    assert result.timeline[0].score_loss == 0
    assert result.timeline[0].evidence.model_sha256 == "a" * 64
