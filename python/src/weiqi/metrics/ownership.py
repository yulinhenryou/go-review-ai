"""Ownership facts of every move: ownership change and group status changes
(ARCHITECTURE §6.2).

KataGo's ownership gives each point a value in [-1, 1], positive where it
expects Black to own the point at the end. For a chain of stones, its mean
ownership in its own color's perspective says how safe the engine thinks it
is: near 1 alive, near -1 dead. `group_status.v1` classifies that mean with
thresholds that are product settings to calibrate against owner-labelled
positions, not Go truths (ADR-011).

For move *n*, every chain on the board before the move is classified twice
on the same stones, with the ownership of the position before and after the
move; a `GroupStatusChange` is emitted when the class differs, or when the
move captured the chain. Chains come from the rules core. The stone just
played belongs to no chain before the move, so it is not reported here.
Comparing with the end of the recommended variation needs a search of that
position and is left for later.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

import weiqi_core

from weiqi.metrics.errors import MetricInputError
from weiqi.metrics.evidence import Evaluations, evaluated_turns

if TYPE_CHECKING:
    from weiqi_core import Color, Point

    from weiqi.engine import AnalysisRequest, TurnAnalysis

GROUP_STATUS: Final = "group_status.v1"

type GroupStatus = Literal["alive", "dead", "unsettled"]


@dataclass(frozen=True, slots=True)
class StatusThresholds:
    """Mean ownership, in the chain's own perspective, that decides its class."""

    alive: float = 0.6
    """At or above: alive."""
    dead: float = -0.6
    """At or below: dead. Between the two: unsettled."""

    def __post_init__(self) -> None:
        values = (self.alive, self.dead)
        if (
            any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in values
            )
            or not -1 <= self.dead < self.alive <= 1
        ):
            raise MetricInputError(
                "invalid_threshold", "need finite thresholds with -1 <= dead < alive <= 1"
            )

    def classify(self, mean_ownership: float) -> GroupStatus:
        if mean_ownership >= self.alive:
            return "alive"
        if mean_ownership <= self.dead:
            return "dead"
        return "unsettled"


DEFAULT_THRESHOLDS: Final = StatusThresholds()


@dataclass(frozen=True, slots=True)
class GroupStatusChange:
    """A chain whose status differs before and after a move."""

    color: Color
    """The chain's color, which may be the mover's or the opponent's."""
    stones: tuple[Point, ...]
    """The chain before the move, row-major order."""
    before: GroupStatus
    after: GroupStatus | Literal["captured"]
    ownership_before: float
    """Mean ownership of the stones before the move, in the chain's perspective."""
    ownership_after: float | None
    """The same after the move; `None` when the move captured the chain."""


@dataclass(frozen=True, slots=True)
class OwnershipFacts:
    """Ownership evidence for one move. `ownership_delta` is `None` when
    either position was analysed without ownership; then `group_changes` is
    empty because nothing could be checked, not because nothing changed."""

    move_number: int
    color: Color
    ownership_delta: tuple[float, ...] | None
    """Per point, row-major: ownership after minus before, mover's perspective."""
    group_changes: tuple[GroupStatusChange, ...]
    definition: str = GROUP_STATUS


def ownership_facts(
    evaluations: Evaluations, thresholds: StatusThresholds = DEFAULT_THRESHOLDS
) -> tuple[OwnershipFacts, ...]:
    """Ownership facts for every move of the request, in order."""
    request = evaluations.request
    turns = evaluated_turns(evaluations)
    chains = _chains_by_turn(request)
    facts = []
    for number in range(1, len(request.moves) + 1):
        color = request.moves[number - 1][0]
        before = _ownership(turns.get(number - 1))
        after = _ownership(turns.get(number))
        if before is None or after is None:
            facts.append(OwnershipFacts(number, color, None, ()))
            continue
        sign = _sign(color)
        delta = tuple(sign * (a - b) for a, b in zip(after, before, strict=True))
        changes = _group_changes(
            chains[number - 1], chains[number], before, after, request.width, thresholds
        )
        facts.append(OwnershipFacts(number, color, delta, changes))
    return tuple(facts)


def _ownership(analysis: TurnAnalysis | None) -> tuple[float, ...] | None:
    return None if analysis is None else analysis.ownership_black


def _sign(color: Color) -> int:
    return 1 if color == "B" else -1


def _chains_by_turn(request: AnalysisRequest) -> list[list[weiqi_core.Chain]]:
    """The chains of every position 0..len(moves), from the rules core."""
    game = weiqi_core.Game(
        request.width,
        request.height,
        weiqi_core.Rules.from_name(request.rules),
        request.komi,
        weiqi_core.Setup(
            list(request.initial_black), list(request.initial_white), request.initial_player
        ),
    )
    chains = [game.chains()]
    for color, move in request.moves:
        # Record mode, as in the request's own replay: recorded violations are applied.
        game.play_as(color, move, "record")
        chains.append(game.chains())
    return chains


def _mean(ownership: Sequence[float], stones: Sequence[Point], width: int, color: Color) -> float:
    return _sign(color) * sum(ownership[y * width + x] for x, y in stones) / len(stones)


def _group_changes(
    chains_before: Sequence[weiqi_core.Chain],
    chains_after: Sequence[weiqi_core.Chain],
    before: Sequence[float],
    after: Sequence[float],
    width: int,
    thresholds: StatusThresholds,
) -> tuple[GroupStatusChange, ...]:
    # Which color holds each stone after the move; captured stones are absent.
    holder: Mapping[Point, Color] = {
        stone: chain.color for chain in chains_after for stone in chain.stones
    }
    changes = []
    for chain in chains_before:
        stones = tuple(chain.stones)
        mean_before = _mean(before, stones, width, chain.color)
        status_before = thresholds.classify(mean_before)
        if holder.get(stones[0]) != chain.color:
            # A capture removes whole chains, so one missing stone means all are.
            changes.append(
                GroupStatusChange(chain.color, stones, status_before, "captured", mean_before, None)
            )
            continue
        mean_after = _mean(after, stones, width, chain.color)
        status_after = thresholds.classify(mean_after)
        if status_after != status_before:
            changes.append(
                GroupStatusChange(
                    chain.color, stones, status_before, status_after, mean_before, mean_after
                )
            )
    return tuple(changes)
