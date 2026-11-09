"""Turning points, `turning_points.v1` (ARCHITECTURE §6.2, MIGRATION R09).

The root winrate of every analysed position, in Black's perspective, falls
into one of three bands: Black ahead, close, or White ahead. A move is a
turning point when the band after it is worse for the mover than the band
before it, for example a Black move after which Black is no longer ahead,
and the mover's winrate fell by at least `min_drop_pp` in that move: on the
first real run (the 235-move game at 32 visits) a winrate hovering near a
limit otherwise made turning points of moves that changed it by 1 to 9
points. A band change in the mover's favour is not reported: it usually
shows the opponent's earlier mistake being recognised, or search noise.

The band limits are product settings to calibrate (ADR-011). The prototype's
heuristics (winrate cliff, clustering radius) were a reference only; none of
their thresholds is copied. Each turning point also states its share of the
mover's total loss in the game (primary definition, ADR-P02), so a band
change caused by a small loss near a limit can be told apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from weiqi.metrics.errors import MetricInputError
from weiqi.metrics.evidence import Evaluations, evaluated_turns
from weiqi.metrics.loss import move_metrics

if TYPE_CHECKING:
    from weiqi_core import Color

TURNING_POINTS: Final = "turning_points.v1"

type Band = Literal["white_ahead", "close", "black_ahead"]
_RANK: Final[dict[Band, int]] = {"white_ahead": 0, "close": 1, "black_ahead": 2}


@dataclass(frozen=True, slots=True)
class WinrateBands:
    """Limits on Black's root winrate."""

    black_ahead: float = 0.7
    """At or above: Black is ahead."""
    white_ahead: float = 0.3
    """At or below: White is ahead. Between the two: close."""
    min_drop_pp: float = 10.0
    """The mover's winrate must also fall by at least this many percentage
    points in the move, so a winrate hovering at a limit does not make a
    turning point of every move."""

    def __post_init__(self) -> None:
        values = (self.black_ahead, self.white_ahead, self.min_drop_pp)
        if (
            any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in values
            )
            or not 0 <= self.white_ahead < self.black_ahead <= 1
            or not 0 <= self.min_drop_pp <= 100
        ):
            raise MetricInputError(
                "invalid_threshold",
                "need 0 <= white_ahead < black_ahead <= 1 and 0 <= min_drop_pp <= 100",
            )

    def band(self, winrate_black: float) -> Band:
        if winrate_black >= self.black_ahead:
            return "black_ahead"
        if winrate_black <= self.white_ahead:
            return "white_ahead"
        return "close"


DEFAULT_BANDS: Final = WinrateBands()


@dataclass(frozen=True, slots=True)
class TurningPoint:
    """A move after which the game's band moved against the mover."""

    move_number: int
    color: Color
    band_before: Band
    band_after: Band
    winrate_black_before: float
    winrate_black_after: float
    share_of_loss: float | None
    """This move's primary loss over the mover's total primary loss in the
    game; `None` when the loss or the total is missing or zero."""
    definition: str = TURNING_POINTS


def turning_points(
    evaluations: Evaluations, bands: WinrateBands = DEFAULT_BANDS
) -> tuple[TurningPoint, ...]:
    """Turning points in move order. Moves whose position before or after has
    no root winrate cannot be turning points; they are not guessed."""
    turns = evaluated_turns(evaluations)
    metrics = move_metrics(evaluations)
    totals: dict[Color, float] = {"B": 0.0, "W": 0.0}
    for item in metrics:
        totals[item.color] += item.primary.score_loss or 0.0

    points = []
    for item in metrics:
        before, after = turns.get(item.move_number - 1), turns.get(item.move_number)
        if before is None or after is None:
            continue
        rate_before, rate_after = before.root.winrate_black, after.root.winrate_black
        if rate_before is None or rate_after is None:
            continue
        band_before, band_after = bands.band(rate_before), bands.band(rate_after)
        change = _RANK[band_after] - _RANK[band_before]
        # A Black move is against Black when the rank falls, a White move when it rises.
        if change == 0 or (change > 0) == (item.color == "B"):
            continue
        drop = item.sequential.winrate_delta_pp
        if drop is None or -drop < bands.min_drop_pp:
            continue
        loss, total = item.primary.score_loss, totals[item.color]
        share = loss / total if loss and total else None
        points.append(
            TurningPoint(
                item.move_number,
                item.color,
                band_before,
                band_after,
                rate_before,
                rate_after,
                share,
            )
        )
    return tuple(points)
