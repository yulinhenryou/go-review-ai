"""Ownership change and group status changes (`group_status.v1`) on small
boards with hand-set ownership. Fixed evidence only; the recorded real
exchange is checked in `test_metrics_recorded.py`."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING

import pytest
from metric_fixtures import evaluated, turn

from weiqi.engine import AnalysisRequest
from weiqi.metrics import (
    DEFAULT_THRESHOLDS,
    GroupStatusChange,
    MetricInputError,
    StatusThresholds,
    ownership_facts,
)

if TYPE_CHECKING:
    from weiqi_core import Color, Move, Point

SIZE = 5


def small(
    moves: tuple[tuple[Color, Move], ...], initial_black: tuple[Point, ...] = ()
) -> AnalysisRequest:
    return AnalysisRequest(
        width=SIZE,
        height=SIZE,
        rules="chinese",
        komi=0.5,
        moves=moves,
        analyze_turns=tuple(range(len(moves) + 1)),
        max_visits=100,
        include_ownership=True,
        initial_black=initial_black,
        initial_player="W" if initial_black else "B",
    )


def own(values: Mapping[Point, float], default: float = 0.0) -> list[float]:
    """A row-major ownership map (Black positive) with a few points set."""
    grid = [default] * (SIZE * SIZE)
    for (x, y), value in values.items():
        grid[y * SIZE + x] = value
    return grid


def test_status_changes_of_both_colours_are_reported_on_the_same_stones() -> None:
    req = small((("B", (1, 1)), ("W", (3, 3)), ("B", (0, 4))))
    results = [
        turn(req, 0, (0.0, 0.5), ownership=own({})),
        turn(req, 1, (0.0, 0.5), ownership=own({(1, 1): 0.9})),
        turn(req, 2, (0.0, 0.5), ownership=own({(1, 1): 0.9, (3, 3): -0.9})),
        # After Black's third move: Black (1,1) unsettled, White (3,3) dead.
        turn(req, 3, (0.0, 0.5), ownership=own({(1, 1): 0.2, (3, 3): 0.8, (0, 4): 1.0})),
    ]
    facts = ownership_facts(evaluated(req, results))
    assert [f.move_number for f in facts] == [1, 2, 3]
    assert facts[0].group_changes == () and facts[1].group_changes == ()
    third = facts[2]
    assert third.definition == "group_status.v1"
    assert third.group_changes == (
        GroupStatusChange("B", ((1, 1),), "alive", "unsettled", 0.9, 0.2),
        GroupStatusChange("W", ((3, 3),), "alive", "dead", 0.9, -0.8),
    )
    # The stone just played has no "before", so it is not a change.
    assert all((0, 4) not in c.stones for c in third.group_changes)


def test_ownership_delta_is_in_the_movers_perspective() -> None:
    req = small((("B", (1, 1)), ("W", (3, 3))))
    results = [
        turn(req, 0, (0.0, 0.5), ownership=own({}, default=0.1)),
        turn(req, 1, (0.0, 0.5), ownership=own({(1, 1): 0.9}, default=0.1)),
        turn(req, 2, (0.0, 0.5), ownership=own({(1, 1): 0.9, (3, 3): -0.5}, default=0.1)),
    ]
    first, second = ownership_facts(evaluated(req, results))
    assert first.ownership_delta is not None and second.ownership_delta is not None
    assert len(first.ownership_delta) == SIZE * SIZE
    assert first.ownership_delta[1 * SIZE + 1] == pytest.approx(0.8)  # Black gained
    assert second.ownership_delta[3 * SIZE + 3] == pytest.approx(0.6)  # White gained
    assert second.ownership_delta[0] == pytest.approx(0.0)


def test_a_captured_chain_is_reported_as_captured() -> None:
    # White's corner stone at (0, 0) is captured by Black's (0, 1).
    req = small((("B", (1, 0)), ("W", (0, 0)), ("B", (0, 1))))
    results = [
        turn(req, 0, (0.0, 0.5), ownership=own({})),
        turn(req, 1, (0.0, 0.5), ownership=own({(1, 0): 0.9})),
        turn(req, 2, (0.0, 0.5), ownership=own({(1, 0): 0.9, (0, 0): 0.7})),
        turn(req, 3, (0.0, 0.5), ownership=own({(1, 0): 0.95, (0, 0): 1.0, (0, 1): 0.95})),
    ]
    third = ownership_facts(evaluated(req, results))[2]
    assert third.group_changes == (
        GroupStatusChange("W", ((0, 0),), "dead", "captured", -0.7, None),
    )


def test_a_chain_is_judged_by_the_mean_of_its_stones() -> None:
    # Two black stones, one safe and one shaky: the mean decides.
    req = small((("B", (1, 1)), ("W", (4, 4)), ("B", (1, 2)), ("W", (4, 3))))
    stones = {(1, 1): 0.9, (1, 2): 0.5}
    results = [
        turn(req, 3, (0.0, 0.5), ownership=own({**stones, (4, 4): -0.9})),
        turn(req, 4, (0.0, 0.5), ownership=own({(1, 1): 0.9, (1, 2): 0.1, (4, 4): -0.9})),
    ]
    fourth = ownership_facts(evaluated(req, results))[3]
    (change,) = fourth.group_changes
    assert change.stones == ((1, 1), (1, 2))
    assert (change.before, change.after) == ("alive", "unsettled")
    assert change.ownership_before == pytest.approx(0.7)
    assert change.ownership_after == pytest.approx(0.5)


def test_setup_stones_are_chains_from_the_first_move() -> None:
    # A handicap-like setup stone; the prototype could not replay setup at all.
    req = small((("W", (3, 3)),), initial_black=((1, 1),))
    results = [
        turn(req, 0, (0.0, 0.5), ownership=own({(1, 1): 0.9})),
        turn(req, 1, (0.0, 0.5), ownership=own({(1, 1): -0.7, (3, 3): -0.9})),
    ]
    (fact,) = ownership_facts(evaluated(req, results))
    assert fact.color == "W"
    assert fact.group_changes == (GroupStatusChange("B", ((1, 1),), "alive", "dead", 0.9, -0.7),)


def test_without_ownership_nothing_is_claimed() -> None:
    req = small((("B", (1, 1)), ("W", (3, 3))))
    results = [
        turn(req, 0, (0.0, 0.5), ownership=own({})),
        turn(req, 1, (0.0, 0.5)),  # analysed without ownership
        turn(req, 2, (0.0, 0.5), ownership=own({})),
    ]
    for fact in ownership_facts(evaluated(req, results)):
        assert fact.ownership_delta is None
        assert fact.group_changes == ()


@pytest.mark.parametrize(
    ("mean", "status"),
    [
        (1.0, "alive"),
        (0.6, "alive"),
        (0.599, "unsettled"),
        (0.0, "unsettled"),
        (-0.599, "unsettled"),
        (-0.6, "dead"),
        (-1.0, "dead"),
    ],
)
def test_default_status_boundaries(mean: float, status: str) -> None:
    assert DEFAULT_THRESHOLDS.classify(mean) == status


@pytest.mark.parametrize(
    ("alive", "dead"), [(0.5, 0.5), (1.5, -0.6), (0.6, -1.5), (math.nan, -0.6), (True, -0.6)]
)
def test_bad_status_thresholds_fail(alive: float, dead: float) -> None:
    with pytest.raises(MetricInputError) as error:
        StatusThresholds(alive=alive, dead=dead)
    assert error.value.code == "invalid_threshold"


def test_thresholds_are_a_setting() -> None:
    req = small((("B", (1, 1)), ("W", (3, 3))))
    results = [
        turn(req, 1, (0.0, 0.5), ownership=own({(1, 1): 0.9})),
        turn(req, 2, (0.0, 0.5), ownership=own({(1, 1): 0.55})),
    ]
    assert ownership_facts(evaluated(req, results))[1].group_changes != ()
    loose = StatusThresholds(alive=0.5, dead=-0.5)
    assert ownership_facts(evaluated(req, results), loose)[1].group_changes == ()
