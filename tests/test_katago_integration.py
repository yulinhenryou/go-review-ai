"""Opt in with RUN_KATAGO_INTEGRATION=1 and the documented engine paths."""
import os

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
