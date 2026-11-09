"""The review result `review.v1` from fixed evidence (MIGRATION R05, R06):
coverage and partial results, chronology apart from ranking, chart values
in Black's perspective, codes without text, and determinism. Ports the
intent of the prototype's `tests/test_review_result.py`."""

from __future__ import annotations

import json
import re

import pytest
from metric_fixtures import Evaluated, played_search
from review_fixtures import OTHER, ROOTS, review, setup

from weiqi.engine import TurnResult
from weiqi.metrics import SeverityBand
from weiqi.review import ReviewSettings, build_result


def test_chronology_is_separate_from_the_ranked_mistakes() -> None:
    result = review(ROOTS)
    assert result.schema == "review.v1"
    assert result.status == "complete"
    assert [m.move_number for m in result.timeline] == [1, 2, 3, 4]
    assert [m.score_loss for m in result.timeline] == [5.0, 9.0, 1.0, 4.0]
    # Default band 4 / 8 (ADR-P17), ranked by loss.
    assert [(m.move_number, m.severity) for m in result.mistakes] == [
        (2, "severe"),
        (1, "mistake"),
        (4, "mistake"),
    ]
    assert [m.severity for m in result.timeline] == ["mistake", "severe", None, "mistake"]
    method = result.method
    assert (method.score_loss, method.mistake_threshold, method.severe_threshold) == (
        "score_loss.sequential.v1",
        4.0,
        8.0,
    )
    assert method.thresholds_calibrated is False


def test_a_limit_shortens_the_ranking_but_not_the_timeline() -> None:
    result = review(ROOTS, settings=ReviewSettings(mistake_limit=1))
    assert [m.move_number for m in result.mistakes] == [2]
    assert [m.severity for m in result.timeline] == ["mistake", "severe", None, "mistake"]
    legacy_band = ReviewSettings(band=SeverityBand("legacy", 3.0, 5.0))
    assert len(review(ROOTS, settings=legacy_band).mistakes) == 3


def test_black_chart_values_and_mover_losses_agree_for_both_colours() -> None:
    for item in review(ROOTS).timeline:
        sign = 1 if item.color == "B" else -1
        assert item.score_black_before is not None and item.score_black_after is not None
        assert item.raw_score_loss is not None
        assert item.score_black_before - item.score_black_after == pytest.approx(
            sign * item.raw_score_loss
        )


def test_a_missing_turn_makes_the_result_partial_not_clean() -> None:
    # Prototype: test_missing_score_is_partial_not_clean_...
    result = review([ROOTS[0], None, *ROOTS[2:]])
    assert result.status == "partial"
    assert result.coverage.missing_score_moves == (1, 2)
    assert result.coverage.moves_with_score == 2
    assert result.timeline[0].severity is None and result.timeline[0].score_loss is None
    assert "missing_score_evidence" in result.warnings


def test_a_missing_winrate_keeps_the_point_loss() -> None:
    roots = list(ROOTS)
    roots[2] = (4.0, None)
    result = review(roots)
    assert result.status == "partial"
    assert result.coverage.missing_winrate_moves == (2, 3)
    assert result.timeline[1].score_loss == 9.0 and result.timeline[1].severity == "severe"
    assert result.timeline[1].winrate_delta_pp is None


def test_missing_ownership_makes_the_result_partial() -> None:
    result = review(ROOTS, ownership=None)
    assert result.status == "partial"
    assert result.coverage.missing_ownership_moves == (1, 2, 3, 4)
    assert all(not m.ownership_evaluated and m.group_changes == () for m in result.timeline)


def test_an_unevaluated_final_position_makes_the_result_partial() -> None:
    # Prototype: test_missing_current_evaluation_makes_report_partial.
    result = review([*ROOTS[:4], (None, None)])
    assert result.status == "partial"
    assert not result.coverage.current_position_evaluated
    assert "missing_current_value" in result.warnings


def test_a_final_position_without_candidates_invents_no_recommendation() -> None:
    # Prototype: test_terminal_root_values_without_candidates_...
    game, evaluations = setup(ROOTS)
    last = evaluations.results[-1]
    bare = TurnResult(
        type(last.analysis)(
            last.analysis.turn, last.analysis.root, (), last.analysis.ownership_black
        ),
        last.query_key,
        (),
    )
    result = build_result(
        game,
        Evaluated(evaluations.request, evaluations.identity, (*evaluations.results[:-1], bare)),
        [],
        ReviewSettings(),
    )
    assert result.current_position.evaluated and result.current_position.best_move is None
    assert result.current_position.candidates == ()
    assert "no_candidate_moves" in result.warnings


def test_the_pv_is_the_recommendations_own() -> None:
    # Prototype: test_pv_comes_only_from_its_recommendation_...
    for item in review(ROOTS).timeline:
        assert item.best_move == OTHER
        assert item.pv == (OTHER,)


def test_a_pass_is_a_move_not_missing_evidence() -> None:
    last = review(ROOTS).timeline[-1]
    assert last.move == "pass" and last.score_loss == 4.0


def test_same_root_values_and_played_searches_are_carried() -> None:
    game, evaluations = setup(ROOTS)
    searches = [played_search(evaluations.request, n, (0.0, 0.5)) for n in range(len(ROOTS) - 1)]
    result = build_result(game, evaluations, searches, ReviewSettings())
    assert result.coverage.played_move_searches == 4
    first = result.timeline[0]
    assert first.same_root_raw_score_loss == pytest.approx(0.0)
    assert "separate_search" in first.same_root_flags
    assert "separate_search" in result.diagnostic_warnings
    assert "separate_search" not in result.warnings


def test_engine_warnings_and_noise_are_kept_as_codes() -> None:
    roots = list(ROOTS)
    roots[3] = (5.0, 0.72)  # Black gains 1 by the sequential values: noise
    result = review(roots, warnings={1: ("low_visits_root",)})
    assert {"low_visits_root", "negative_difference_search_noise"} <= set(result.warnings)
    assert result.timeline[2].raw_score_loss == -1.0 and result.timeline[2].score_loss == 0.0


def test_same_root_gaps_are_not_primary_warnings() -> None:
    # Without played-move searches every same-root value is missing; the
    # primary evidence is still complete.
    result = review(ROOTS)
    assert result.status == "complete"
    assert {"played_move_not_searched", "missing_score_evidence"} <= set(result.diagnostic_warnings)
    assert result.warnings == ()


def test_the_game_summary_is_metadata_only() -> None:
    game = review(ROOTS).game
    assert (game.black_player, game.white_player, game.result_text) == ("Alice", "Bob", "B+R")
    assert game.record_status == "result_recorded"
    assert (game.rules, game.komi, game.width, game.setup_black) == ("chinese", 7.5, 19, 0)


def test_json_is_canonical_text_free_and_deterministic() -> None:
    first, second = review(ROOTS), review(ROOTS)
    text = first.to_json()
    assert text == second.to_json()
    data = json.loads(text)
    assert data["schema"] == "review.v1"
    assert data["timeline"][3]["move"] == "pass"
    # Results carry codes and numbers; sentences come from the locale catalogs.
    assert not re.search(r"[一-鿿]", text)
    assert not {"summary", "label", "note", "explanation"} & set(data)
