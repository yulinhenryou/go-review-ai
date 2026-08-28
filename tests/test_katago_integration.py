"""Opt in with RUN_KATAGO_INTEGRATION=1 and the documented engine paths."""
import os
import json
from pathlib import Path

import pytest

from src.analyzer import analyze_game_state
from src.katago_client import KataGoClient
from src.review_service import build_structured_review_for_game
from src.sgf_parser import parse_sgf, parse_sgf_file

pytestmark = pytest.mark.skipif(os.environ.get("RUN_KATAGO_INTEGRATION") != "1", reason="Real KataGo is opt-in")


def test_real_model_analysis_is_traceable_and_not_a_fixed_mock():
    game = parse_sgf_file("samples/sample_game.sgf")
    value = build_structured_review_for_game(game, KataGoClient.from_environment(max_visits=32))
    assert value.engine_source == "katago"
    assert len(value.timeline) == len(game.moves)
    for item in value.timeline:
        assert item.evidence and item.evidence.engine_version
        assert len(item.evidence.model_sha256) == 64
        assert item.evidence.root_visits > 0
        assert item.played_candidate and item.played_candidate.visits > 0
        assert item.played_candidate.move.sgf == item.played_move.sgf
        assert item.raw_score_loss is not None
        assert item.score_loss == max(0, item.raw_score_loss)
        assert item.score_black_before - item.score_black_after == pytest.approx(
            item.raw_score_loss * (1 if item.color == "B" else -1))
    assert all(c.pv[0].move == c.move.sgf for c in value.current_position.top_candidates if c.pv)


@pytest.mark.parametrize("rules", ["Japanese", "Chinese"])
def test_real_passes_and_end_of_record(rules):
    game = parse_sgf(f"(;FF[4]GM[1]SZ[19]RU[{rules}]KM[6.5];B[pd];W[dd];B[];W[])")
    result = analyze_game_state(game, KataGoClient.from_environment(max_visits=16))
    assert result.move_results[-1].engine_analysis.played_candidate.move == "pass"
    assert result.move_results[-1].estimated_loss is not None
    assert result.current_position.evidence.played_source == "not_applicable"


@pytest.mark.parametrize("rerun", [1, 2])
def test_real_obvious_mistakes_have_traceable_factual_reports_with_tolerance(rerun):
    reference = json.loads(Path("docs/evidence/m3-report.json").read_text())
    game = parse_sgf_file(reference["sample"])
    review = build_structured_review_for_game(game, KataGoClient.from_environment(max_visits=reference["max_visits"]))
    assert review.status == "complete"
    assert review.coverage.moves_evaluated == 6
    assert {item.move_number for item in review.selected_mistakes} == {1, 3, 5}
    evidence = review.current_position.evidence
    same_context = evidence.model_sha256 == reference["model_sha256"] and evidence.config_sha256 == reference["config_sha256"]
    expected = {item["move_number"]: item["score_loss"] for item in reference["selected_mistakes"]}
    for item in review.selected_mistakes:
        assert item.score_loss >= 3
        if same_context:
            assert item.score_loss == pytest.approx(expected[item.move_number], abs=4)
        assert item.pv and item.pv[0].move == item.recommended_move.sgf
        assert item.pv[0].color == item.color
        assert item.played_candidate.move.sgf == item.played_move.sgf
        assert f"估计损失 {item.score_loss:.2f} 目" in item.summary
    assert "主战场" not in json.dumps(review.to_dict(), ensure_ascii=False)
