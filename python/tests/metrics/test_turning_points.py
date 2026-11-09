"""Turning points (`turning_points.v1`): winrate bands crossed against the
mover, with the move's share of the mover's total loss."""

from __future__ import annotations

import math

import pytest
from metric_fixtures import evaluated, moves, request, turn

from weiqi.metrics import (
    DEFAULT_BANDS,
    MetricInputError,
    TurningPoint,
    WinrateBands,
    turning_points,
)


def test_only_band_changes_against_the_mover_are_turning_points() -> None:
    req = request(moves(4))
    # (Black score lead, Black winrate) per turn.
    results = [
        turn(req, 0, (3.0, 0.75)),  # Black ahead
        turn(req, 1, (0.0, 0.50)),  # B lost 3 and fell to close: turning point
        turn(req, 2, (4.0, 0.80)),  # W lost 4 and Black is ahead again: turning point
        turn(req, 3, (2.0, 0.85)),  # B lost 2, no band change
        turn(req, 4, (-6.0, 0.20)),  # W gained: a change in the mover's favour
    ]
    assert turning_points(evaluated(req, results)) == (
        TurningPoint(1, "B", "black_ahead", "close", 0.75, 0.50, 3 / 5),
        TurningPoint(2, "W", "close", "black_ahead", 0.50, 0.80, 1.0),
    )


def test_a_change_without_a_loss_has_no_share() -> None:
    req = request(moves(1))
    results = [turn(req, 0, (0.0, 0.75)), turn(req, 1, (0.5, 0.60))]  # noise in score
    (point,) = turning_points(evaluated(req, results))
    assert (point.band_before, point.band_after) == ("black_ahead", "close")
    assert point.share_of_loss is None
    assert point.definition == "turning_points.v1"


def test_a_winrate_hovering_at_a_limit_is_not_a_turning_point() -> None:
    # The pattern of moves 46-51 of the 235-move game at 32 visits, where
    # White moves first: each move crosses 0.7 against the mover by 1-9 points.
    req = request(moves(5))
    rates = [0.5, 0.67, 0.71, 0.62, 0.70, 0.69]
    results = [turn(req, n, (0.0, rate)) for n, rate in enumerate(rates)]
    assert turning_points(evaluated(req, results)) == ()
    every_crossing = WinrateBands(min_drop_pp=0.0)
    numbers = [p.move_number for p in turning_points(evaluated(req, results), every_crossing)]
    assert numbers == [2, 3, 4, 5]


def test_moves_without_winrates_are_not_guessed() -> None:
    req = request(moves(2))
    results = [turn(req, 0, (0.0, 0.9)), turn(req, 1, (0.0, None)), turn(req, 2, (0.0, 0.1))]
    assert turning_points(evaluated(req, results)) == ()
    assert turning_points(evaluated(req, [turn(req, 0, (0.0, 0.9))])) == ()


@pytest.mark.parametrize(
    ("rate", "band"),
    [
        (1.0, "black_ahead"),
        (0.7, "black_ahead"),
        (0.699, "close"),
        (0.301, "close"),
        (0.3, "white_ahead"),
        (0.0, "white_ahead"),
    ],
)
def test_default_band_limits(rate: float, band: str) -> None:
    assert DEFAULT_BANDS.band(rate) == band


@pytest.mark.parametrize(
    ("black", "white", "drop"),
    [
        (0.5, 0.5, 10),
        (1.1, 0.3, 10),
        (0.7, -0.1, 10),
        (math.inf, 0.3, 10),
        (0.7, 0.3, -1),
        (0.7, 0.3, 101),
        (0.7, 0.3, math.nan),
    ],
)
def test_bad_band_limits_fail(black: float, white: float, drop: float) -> None:
    with pytest.raises(MetricInputError):
        WinrateBands(black_ahead=black, white_ahead=white, min_drop_pp=drop)
