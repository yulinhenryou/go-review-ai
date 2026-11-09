"""Checks that engine results belong to the request they are used with.

Every metric starts here: each result's `query_key` is recomputed from the
request and the engine identity, so values from another game, rule set,
komi, search setting or engine cannot be mixed in.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

from weiqi.metrics.errors import MetricInputError

if TYPE_CHECKING:
    from weiqi.engine import AnalysisRequest, EngineIdentity, TurnAnalysis, TurnResult


class Evaluations(Protocol):
    """Engine results for one request: `GameAnalysis` or `CachedAnalysis`."""

    @property
    def request(self) -> AnalysisRequest: ...
    @property
    def identity(self) -> EngineIdentity: ...
    @property
    def results(self) -> tuple[TurnResult, ...]: ...


def checked_turns(
    request: AnalysisRequest, identity: EngineIdentity, results: Iterable[TurnResult]
) -> dict[int, TurnAnalysis]:
    """The analyses by turn, after checking each belongs to `request` on `identity`."""
    turns: dict[int, TurnAnalysis] = {}
    for result in results:
        analysis = result.analysis
        turn = analysis.turn
        if not 0 <= turn <= len(request.moves):
            raise MetricInputError("incomparable_context", f"turn {turn} is not in the game")
        if turn in turns:
            raise MetricInputError("duplicate_turn", f"turn {turn} is evaluated twice")
        if result.query_key != request.query_key(identity, turn):
            raise MetricInputError(
                "incomparable_context",
                f"the evaluation of turn {turn} was made for another request or engine",
            )
        if analysis.root.current_player != request.players[turn]:
            raise MetricInputError(
                "incomparable_context", f"turn {turn} was evaluated for the wrong player"
            )
        turns[turn] = analysis
    return turns


def evaluated_turns(evaluations: Evaluations) -> dict[int, TurnAnalysis]:
    """`checked_turns` of a whole set of evaluations."""
    return checked_turns(evaluations.request, evaluations.identity, evaluations.results)
