"""Severity bands and mistake ranking. Ports the selection cases of the
prototype's `tests/test_mistake_selector.py` (MIGRATION R02 to R05) with the
default band of ADR-P17 (4.0 / 8.0) and, where a case is about the
prototype's numbers, an explicit 3.0 / 5.0 band."""

from __future__ import annotations

import math

import pytest
from metric_fixtures import metrics

from weiqi.metrics import (
    DEFAULT_BAND,
    DEFAULT_CALIBRATION,
    CalibrationTable,
    LossEstimate,
    MetricInputError,
    MoveMetrics,
    SeverityBand,
    select_mistakes,
)

LEGACY = SeverityBand(name="legacy", mistake=3.0, severe=5.0)


def losses(*values: float | None) -> list[MoveMetrics]:
    return [metrics(number, value) for number, value in enumerate(values, start=1)]


def test_the_default_band_is_four_and_eight_points() -> None:
    assert (DEFAULT_BAND.mistake, DEFAULT_BAND.severe) == (4.0, 8.0)
    assert DEFAULT_CALIBRATION.band("default") is DEFAULT_BAND
    assert DEFAULT_CALIBRATION.version == "severity.v1"


@pytest.mark.parametrize(
    ("loss", "severity"),
    [
        (None, None),
        (-1.0, None),
        (0.0, None),
        (3.999999, None),
        (4.0, "mistake"),
        (7.999999, "mistake"),
        (8.0, "severe"),
    ],
)
def test_exact_default_boundaries(loss: float | None, severity: str | None) -> None:
    assert DEFAULT_BAND.classify(loss) == severity


@pytest.mark.parametrize(
    ("loss", "severity"),
    [(2.999999, None), (3.0, "mistake"), (4.999999, "mistake"), (5.0, "severe")],
)
def test_exact_boundaries_of_the_prototype_band(loss: float, severity: str | None) -> None:
    assert LEGACY.classify(loss) == severity


def test_unrounded_ranking_ties_and_a_limit_do_not_change_the_full_list() -> None:
    data = losses(3, 5, 5.00001, 7, 5, 8, 9)
    full = select_mistakes(data, LEGACY)
    assert [m.metrics.move_number for m in full] == [7, 6, 4, 3, 2, 5, 1]
    top = select_mistakes(data, LEGACY, limit=5)
    assert [m.metrics.move_number for m in top] == [7, 6, 4, 3, 2]
    assert [m.severity for m in full] == ["severe"] * 6 + ["mistake"]


@pytest.mark.parametrize(("values", "count"), [((0, 2), 0), ((4, 1), 1), ((4, 8, 5), 3)])
def test_no_forced_padding(values: tuple[float, ...], count: int) -> None:
    assert len(select_mistakes(losses(*values), limit=5)) == count


def test_missing_losses_do_not_enter_the_ranking() -> None:
    selected = select_mistakes(losses(None, 4))
    assert [m.metrics.move_number for m in selected] == [2]
    assert selected[0].score_loss == 4
    assert selected[0].definition == "score_loss.sequential.v1"


def test_negative_raw_loss_is_never_selected_even_with_a_zero_threshold() -> None:
    band = SeverityBand(name="zero", mistake=0.0, severe=0.0)
    assert select_mistakes(losses(-2, 0), band) == ()


def test_winrate_cannot_promote_a_small_point_loss() -> None:
    # Prototype: test_winrate_collapse_cannot_promote_small_point_loss. Severity
    # reads only the score loss, so a move with a tiny loss stays unselected
    # whatever its winrate change.
    item = metrics(1, 0.2)
    collapsed = LossEstimate("score_loss.sequential.v1", 0.2, -98.0, ())
    assert select_mistakes([MoveMetrics(1, "B", (0, 0), None, collapsed, item.same_root)]) == ()


def test_the_same_root_definition_can_be_selected_for_comparison() -> None:
    data = [metrics(1, 1.0, same_root=6.0), metrics(2, 9.0, same_root=None)]
    by_same_root = select_mistakes(data, LEGACY, definition="same_root")
    assert [(m.metrics.move_number, m.severity) for m in by_same_root] == [(1, "severe")]
    assert by_same_root[0].definition == "score_loss.same_root.v1"
    assert [m.metrics.move_number for m in select_mistakes(data, LEGACY)] == [2]


@pytest.mark.parametrize(
    ("mistake", "severe"),
    [(math.nan, 8.0), (4.0, math.inf), (-1.0, 8.0), (4.0, 3.0), (True, 8.0)],
)
def test_bad_thresholds_fail(mistake: float, severe: float) -> None:
    with pytest.raises(MetricInputError) as error:
        SeverityBand(name="bad", mistake=mistake, severe=severe)
    assert error.value.code == "invalid_threshold"


@pytest.mark.parametrize("limit", [0, -1, True])
def test_bad_limits_fail(limit: int) -> None:
    with pytest.raises(MetricInputError) as error:
        select_mistakes(losses(5), limit=limit)
    assert error.value.code == "invalid_limit"


def test_calibration_tables_need_unique_names_and_report_unknown_bands() -> None:
    with pytest.raises(MetricInputError):
        CalibrationTable(version="x", bands=(DEFAULT_BAND, DEFAULT_BAND))
    with pytest.raises(MetricInputError):
        CalibrationTable(version="x", bands=())
    with pytest.raises(MetricInputError) as error:
        DEFAULT_CALIBRATION.band("9d")
    assert error.value.code == "unknown_band"
