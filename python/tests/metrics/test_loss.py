"""Score loss and winrate change per move (ADR-P02). Ports the intent of the
prototype's `tests/test_mistake_selector.py` assessment cases (MIGRATION R01,
R05) to both definitions."""

from __future__ import annotations

from dataclasses import replace

import pytest
from metric_fixtures import IDENTITY, Evaluated, evaluated, moves, request, turn

from weiqi.engine import EngineIdentity
from weiqi.metrics import SAME_ROOT, SEQUENTIAL, MetricInputError, move_metrics


def test_sequential_loss_is_root_before_minus_root_after_for_each_mover() -> None:
    req = request(moves(2))
    # Black perspective: B leads by 2, then by -1 after B's move (B lost 3),
    # then by +4 after W's move (W, seeing -(-1) = 1 then -4, lost 5).
    result = move_metrics(
        evaluated(
            req,
            [turn(req, 0, (2.0, 0.6)), turn(req, 1, (-1.0, 0.45)), turn(req, 2, (4.0, 0.7))],
        )
    )
    black, white = result
    assert (black.color, white.color) == ("B", "W")
    assert black.sequential.definition == SEQUENTIAL
    assert black.sequential.raw_score_loss == pytest.approx(3.0)
    assert white.sequential.raw_score_loss == pytest.approx(5.0)
    # Winrate change: after minus before, in the mover's percentage points.
    assert black.sequential.winrate_delta_pp == pytest.approx(-15.0)
    assert white.sequential.winrate_delta_pp == pytest.approx(-25.0)
    assert black.primary is black.sequential
    assert black.sequential.flags == ()


def test_same_root_compares_recommended_and_played_candidates() -> None:
    req = request(moves(2))
    (_, m1), (_, m2) = req.moves
    other = (10, 10)
    results = [
        turn(req, 0, (1.0, 0.55), [(other, (1.5, 0.56)), (m1, (-2.0, 0.40))]),
        # White to move: recommended W score -0.5, played -(+3.5) = -3.5 -> lost 3.
        turn(req, 1, (-1.0, 0.45), [(other, (0.5, 0.50)), (m2, (3.5, 0.70))]),
        turn(req, 2, (4.0, 0.7)),
    ]
    first, second = move_metrics(evaluated(req, results))
    assert first.best_move == other
    assert first.same_root.definition == SAME_ROOT
    assert first.same_root.raw_score_loss == pytest.approx(3.5)
    # Played minus recommended, mover's perspective, percentage points.
    assert first.same_root.winrate_delta_pp == pytest.approx(-16.0)
    assert second.same_root.raw_score_loss == pytest.approx(3.0)
    assert second.same_root.winrate_delta_pp == pytest.approx(-20.0)


def test_playing_the_recommendation_loses_nothing_by_same_root() -> None:
    req = request(moves(1))
    move = req.moves[0][1]
    item = move_metrics(
        evaluated(req, [turn(req, 0, (1.0, 0.5), [(move, (1.0, 0.5))]), turn(req, 1, (1.0, 0.5))])
    )[0]
    assert item.same_root.raw_score_loss == 0.0
    assert item.same_root.score_loss == 0.0
    assert item.same_root.flags == ()


def test_a_played_move_the_search_did_not_consider_is_not_inferred() -> None:
    # Prototype: test_missing_real_played_candidate_is_not_inferred_from_other_values.
    req = request(moves(1))
    item = move_metrics(
        evaluated(
            req, [turn(req, 0, (1.0, 0.5), [((9, 9), (2.0, 0.6))]), turn(req, 1, (-2.0, 0.4))]
        )
    )[0]
    assert item.same_root.raw_score_loss is None
    assert item.same_root.score_loss is None
    assert "played_move_not_searched" in item.same_root.flags
    assert "missing_score_evidence" in item.same_root.flags
    # The sequential value does not need the played candidate.
    assert item.sequential.raw_score_loss == pytest.approx(3.0)


def test_negative_raw_loss_is_noise_not_a_teaching_claim() -> None:
    req = request(moves(1))
    item = move_metrics(evaluated(req, [turn(req, 0, (1.0, 0.5)), turn(req, 1, (3.0, 0.6))]))[0]
    assert item.sequential.raw_score_loss == pytest.approx(-2.0)
    assert item.sequential.score_loss == 0.0
    assert item.sequential.flags == ("negative_difference_search_noise",)


def test_a_missing_turn_leaves_both_neighbouring_moves_without_sequential_values() -> None:
    req = request(moves(3))
    item = move_metrics(
        evaluated(
            req, [turn(req, 0, (0.0, 0.5)), turn(req, 2, (0.0, 0.5)), turn(req, 3, (1.0, 0.6))]
        )
    )
    assert [m.sequential.raw_score_loss for m in item[:2]] == [None, None]
    for m in item[:2]:
        assert {"missing_score_evidence", "missing_winrate_evidence"} <= set(m.sequential.flags)
    # Move 3 (Black) loses -1: Black's lead grew by 1, which is search noise.
    assert item[2].sequential.raw_score_loss == pytest.approx(-1.0)


def test_a_missing_winrate_keeps_the_point_loss_without_a_fabricated_rate() -> None:
    req = request(moves(1))
    item = move_metrics(evaluated(req, [turn(req, 0, (1.0, 0.5)), turn(req, 1, (-5.0, None))]))[0]
    assert item.sequential.raw_score_loss == pytest.approx(6.0)
    assert item.sequential.winrate_delta_pp is None
    assert item.sequential.flags == ("missing_winrate_evidence",)


def test_winrate_change_is_unrounded() -> None:
    req = request(moves(2))
    first, second = move_metrics(
        evaluated(
            req,
            [
                turn(req, 0, (0.0, 0.60005)),
                turn(req, 1, (0.0, 0.59991)),
                turn(req, 2, (0.0, 0.60023)),
            ],
        )
    )
    assert first.sequential.winrate_delta_pp == pytest.approx(-0.014)
    assert second.sequential.winrate_delta_pp == pytest.approx(-0.032)


def test_pass_is_a_move_and_can_be_matched_by_a_candidate() -> None:
    req = request((("B", (3, 3)), ("W", "pass")))
    results = [
        turn(req, 0, (0.0, 0.5)),
        turn(req, 1, (6.0, 0.8), [((15, 15), (5.0, 0.75)), ("pass", (12.0, 0.95))]),
        turn(req, 2, (12.0, 0.95)),
    ]
    second = move_metrics(evaluated(req, results))[1]
    assert second.move == "pass"
    assert second.sequential.raw_score_loss == pytest.approx(6.0)
    assert second.same_root.raw_score_loss == pytest.approx(7.0)


def test_unanalysed_game_gives_every_move_flags_and_no_values() -> None:
    req = request(moves(2))
    for item in move_metrics(evaluated(req, [])):
        assert item.sequential.raw_score_loss is None
        assert item.same_root.raw_score_loss is None
        assert item.best_move is None


@pytest.mark.parametrize(
    "change",
    [
        {"rules": "japanese"},
        {"komi": 6.5},
        {"max_visits": 200},
        {"moves": (("B", (4, 4)), ("W", (1, 0)))},
    ],
)
def test_evaluations_of_another_request_are_rejected(change: dict[str, object]) -> None:
    # Prototype: test_incomparable_context_is_rejected.
    req = request(moves(2))
    results = [turn(req, n, (0.0, 0.5)) for n in range(3)]
    other = replace(req, **change)  # type: ignore[arg-type]
    with pytest.raises(MetricInputError) as error:
        move_metrics(evaluated(other, results))
    assert error.value.code == "incomparable_context"


def test_evaluations_of_another_engine_are_rejected() -> None:
    req = request(moves(1))
    results = [turn(req, n, (0.0, 0.5)) for n in range(2)]
    other = EngineIdentity(
        version="1.16.4",
        model_name=IDENTITY.model_name,
        model_sha256=IDENTITY.model_sha256,
        config_sha256=IDENTITY.config_sha256,
        overrides=IDENTITY.overrides,
    )
    with pytest.raises(MetricInputError) as error:
        move_metrics(Evaluated(req, other, tuple(results)))
    assert error.value.code == "incomparable_context"


def test_duplicate_and_out_of_range_turns_are_rejected() -> None:
    req = request(moves(1))
    first = turn(req, 0, (0.0, 0.5))
    with pytest.raises(MetricInputError) as error:
        move_metrics(evaluated(req, [first, first]))
    assert error.value.code == "duplicate_turn"
    stray = replace(first, analysis=replace(first.analysis, turn=5))
    with pytest.raises(MetricInputError) as error:
        move_metrics(evaluated(req, [stray]))
    assert error.value.code == "incomparable_context"


def test_an_evaluation_for_the_wrong_player_is_rejected() -> None:
    req = request(moves(1))
    first = turn(req, 0, (0.0, 0.5))
    root = replace(first.analysis.root, current_player="W")
    wrong = replace(first, analysis=replace(first.analysis, root=root))
    with pytest.raises(MetricInputError) as error:
        move_metrics(evaluated(req, [wrong]))
    assert error.value.code == "incomparable_context"


def test_finite_inputs_cannot_overflow_the_difference() -> None:
    # Prototype: test_finite_inputs_cannot_overflow_the_score_difference.
    req = request(moves(1))
    results = [turn(req, 0, (1e308, 0.5)), turn(req, 1, (-1e308, 0.5))]
    with pytest.raises(MetricInputError) as error:
        move_metrics(evaluated(req, results))
    assert error.value.code == "non_finite_difference"
