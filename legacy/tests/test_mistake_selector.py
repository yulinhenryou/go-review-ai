from dataclasses import replace

import pytest

from src.analyzer import analyze_game
from src.engine_types import EngineProtocolError
from src.game import GameInputError
from src.mistake_selector import assess_move, print_mistake_summary, select_mistakes_above_threshold, select_top_mistakes
from src.mistake_severity import severity_from_loss
from tests.report_fixtures import FixedEvidenceEngine, game_with_moves


def results(losses):
    return analyze_game(game_with_moves(len(losses)), FixedEvidenceEngine(losses))


@pytest.mark.parametrize("loss,severity", [(None, None), (-1, None), (0, None), (2.999999, None),
                                           (3, "mistake"), (4.999999, "mistake"), (5, "severe")])
def test_exact_threshold_boundaries(loss, severity):
    assert severity_from_loss(loss) == severity


def test_unrounded_ranking_ties_and_top_five_do_not_change_all_markers():
    data = results([3, 5, 5.00001, 7, 5, 8, 9])
    assert [item.move_number for item in select_top_mistakes(data)] == [7, 6, 4, 3, 2]
    assert [item.move_number for item in select_mistakes_above_threshold(data)] == [7, 6, 4, 3, 2, 5, 1]


@pytest.mark.parametrize("losses,count", [([0, 2], 0), ([3, 1], 1), ([3, 5, 4], 3)])
def test_no_forced_padding(losses, count):
    assert len(select_top_mistakes(results(losses))) == count


def test_missing_scores_do_not_enter_ranking_and_winrate_is_optional():
    data = results([None, 4])
    data[1] = replace(data[1], engine_analysis=replace(data[1].engine_analysis, played_winrate=None))
    selected = select_top_mistakes(data)
    assert [item.move_number for item in selected] == [2]
    assert selected[0].winrate_delta_pp is None
    assert "missing_score_evidence" in assess_move(data[0]).warnings


def test_winrate_changes_are_unrounded_percentage_points_for_each_mover():
    for item in results([3, 3]):
        value = replace(item.engine_analysis, winrate=.60005, played_winrate=.59991)
        assessment = assess_move(replace(item, engine_analysis=value))
        assert assessment.winrate_delta_pp == pytest.approx(-.014)
        assert assessment.score_loss == 3


def test_winrate_collapse_cannot_promote_small_point_loss():
    item = results([.2])[0]
    item = replace(item, engine_analysis=replace(item.engine_analysis, winrate=.99, played_winrate=.01))
    assert select_top_mistakes([item]) == []


def test_negative_raw_loss_is_noise_not_a_positive_teaching_claim():
    item = results([-2])[0]
    assert assess_move(item).raw_score_loss == -2
    assert assess_move(item).score_loss == 0
    assert "negative_difference_search_noise" in assess_move(item).warnings
    assert select_top_mistakes([item], loss_threshold=0) == []


def test_options_are_validated_and_configurable(capsys):
    data = results([1, 2.5])
    selected = select_top_mistakes(data, loss_threshold=1, severe_threshold=2, limit=1)
    assert selected[0].severity == "severe"
    print_mistake_summary(selected)
    assert "pp severity=severe" in capsys.readouterr().out


@pytest.mark.parametrize("options", [{"loss_threshold": float("nan")}, {"severe_threshold": float("inf")},
                                      {"severe_threshold": 2}, {"limit": 6}, {"limit": 0}, {"limit": True}])
def test_bad_options_fail(options):
    with pytest.raises(GameInputError):
        select_top_mistakes(results([3]), **options)


@pytest.mark.parametrize("changes", [{"rules": "japanese"}, {"komi": 0}, {"turn_number": 99},
                                      {"score_unit": "utility"}, {"value_perspective": "BLACK"}])
def test_incomparable_context_is_rejected(changes):
    item = results([3])[0]
    value = replace(item.engine_analysis, evidence=replace(item.engine_analysis.evidence, **changes))
    with pytest.raises(EngineProtocolError):
        assess_move(replace(item, engine_analysis=value))


@pytest.mark.parametrize("number", [float("nan"), float("inf"), True, "3"])
def test_nonfinite_scores_cannot_reach_json(number):
    item = results([3])[0]
    with pytest.raises(EngineProtocolError):
        assess_move(replace(item, engine_analysis=replace(item.engine_analysis, played_score_estimate=number)))


def test_missing_real_played_candidate_is_not_inferred_from_other_values():
    item = results([3])[0]
    item = replace(item, engine_analysis=replace(item.engine_analysis, played_candidate=None))
    assert assess_move(item).score_loss is None


def test_finite_inputs_cannot_overflow_the_score_difference():
    item = results([3])[0]
    value = replace(item.engine_analysis, score_estimate=1e308, played_score_estimate=-1e308)
    with pytest.raises(EngineProtocolError):
        assess_move(replace(item, engine_analysis=value))
