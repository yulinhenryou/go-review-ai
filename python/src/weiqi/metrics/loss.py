"""Score loss and winrate change of every move (ARCHITECTURE §6.1, ADR-P02).

Move *n* (1-based) turns the position at turn *n - 1* into the position at
turn *n*. Two definitions are computed from the same evaluations, both in the
mover's perspective, where a positive loss means the move was worse than the
engine's choice:

- `score_loss.sequential.v1` (primary): the root score lead before the move
  minus the root score lead after it; the winrate change is the root winrate
  after minus before, in percentage points.
- `score_loss.same_root.v1` (diagnostic, and the definition legacy uses): in
  the search before the move, the recommended candidate's score lead minus
  the played candidate's; the winrate change is played minus recommended. A
  played move the search did not consider has no value here: it is flagged,
  never inferred from another candidate or position.

When the search before a move gave the played move no value, a separate
search restricted to that move can supply it (`played_moves_to_search`,
`AnalysisRequest.played_move_search`); the value is then flagged
`separate_search`, because it comes from another search tree. A compared
candidate with few visits is flagged `low_visits`.

The raw difference is kept; `score_loss` is `max(0, raw)`, and a negative raw
difference is flagged as search noise rather than praised (ADR-009).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from weiqi.engine import score_for, winrate_for
from weiqi.metrics.errors import MetricInputError

if TYPE_CHECKING:
    from weiqi_core import Color, Move

    from weiqi.engine import (
        AnalysisRequest,
        Candidate,
        EngineIdentity,
        TurnAnalysis,
        TurnResult,
    )

SEQUENTIAL: Final = "score_loss.sequential.v1"
SAME_ROOT: Final = "score_loss.same_root.v1"

MISSING_SCORE: Final = "missing_score_evidence"
MISSING_WINRATE: Final = "missing_winrate_evidence"
NEGATIVE_NOISE: Final = "negative_difference_search_noise"
NOT_SEARCHED: Final = "played_move_not_searched"
SEPARATE_SEARCH: Final = "separate_search"
LOW_VISITS: Final = 16
"""A compared candidate with fewer visits than this (or than `max_visits`,
if smaller) is flagged `low_visits`, as in the prototype."""
LOW_VISITS_FLAG: Final = "low_visits"


class Evaluations(Protocol):
    """Engine results for one request: `GameAnalysis` or `CachedAnalysis`."""

    @property
    def request(self) -> AnalysisRequest: ...
    @property
    def identity(self) -> EngineIdentity: ...
    @property
    def results(self) -> tuple[TurnResult, ...]: ...


@dataclass(frozen=True, slots=True)
class LossEstimate:
    """One definition's values for one move."""

    definition: str
    raw_score_loss: float | None
    """Points, mover's perspective; negative values are kept as recorded."""
    winrate_delta_pp: float | None
    """Percentage points, mover's perspective; negative means worse."""
    flags: tuple[str, ...]
    """Sorted codes such as `missing_score_evidence`."""

    @property
    def score_loss(self) -> float | None:
        """The loss used for severity and ranking: `max(0, raw)`."""
        return None if self.raw_score_loss is None else max(0.0, self.raw_score_loss)


@dataclass(frozen=True, slots=True)
class MoveMetrics:
    """Everything the metrics layer knows about one move."""

    move_number: int
    color: Color
    move: Move
    best_move: Move | None
    """The engine's recommendation in the position before the move, if searched."""
    sequential: LossEstimate
    same_root: LossEstimate

    @property
    def primary(self) -> LossEstimate:
        """The definition used for severity and ranking (ADR-P02)."""
        return self.sequential


def move_metrics(
    evaluations: Evaluations, played_searches: Iterable[Evaluations] = ()
) -> tuple[MoveMetrics, ...]:
    """Metrics for every move of the request, in order.

    Every result must belong to the request and the engine identity it came
    with (its `query_key` is recomputed), so values from another game, rule
    set, komi or engine cannot be mixed in. Turns that were not analysed
    leave the affected moves without values, flagged.

    `played_searches` are restricted searches of played moves (see
    `played_moves_to_search`); each must be exactly
    `request.played_move_search(turn)` on the same engine. The same-root value
    of that move then takes the played move from it, flagged
    `separate_search`.
    """
    request = evaluations.request
    turns = _turns(request, evaluations.identity, evaluations.results)
    searched = _played_searches(evaluations, played_searches)
    return tuple(
        _move(request, turns, searched, number) for number in range(1, len(request.moves) + 1)
    )


def played_moves_to_search(evaluations: Evaluations) -> tuple[int, ...]:
    """Turns whose played move needs a restricted search for its same-root value.

    That is when the search before the move has a recommendation but did not
    give the played move a value: it is missing from the candidates, has no
    score lead, or received no visits (the prototype's rule).
    """
    request = evaluations.request
    turns = _turns(request, evaluations.identity, evaluations.results)
    return tuple(
        turn
        for turn, analysis in sorted(turns.items())
        if turn < len(request.moves) and _needs_search(analysis, request.moves[turn][1])
    )


def _needs_search(before: TurnAnalysis, move: Move) -> bool:
    if not before.candidates:
        return False
    played = _candidate(before, move)
    return played is None or played.score_lead_black is None or not played.visits


def _turns(
    request: AnalysisRequest, identity: EngineIdentity, results: Iterable[TurnResult]
) -> dict[int, TurnAnalysis]:
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


def _played_searches(
    evaluations: Evaluations, searches: Iterable[Evaluations]
) -> dict[int, TurnAnalysis]:
    request = evaluations.request
    found: dict[int, TurnAnalysis] = {}
    for search in searches:
        turns = search.request.analyze_turns
        turn = turns[0]
        if (
            search.identity != evaluations.identity
            or len(turns) != 1
            or not 0 <= turn < len(request.moves)
            or search.request != request.played_move_search(turn)
        ):
            raise MetricInputError(
                "incomparable_context",
                "a played-move search was made for another request or engine",
            )
        if turn in found:
            raise MetricInputError("duplicate_turn", f"turn {turn} is searched twice")
        analysed = _turns(search.request, search.identity, search.results)
        if turn in analysed:
            found[turn] = analysed[turn]
    return found


def _move(
    request: AnalysisRequest,
    turns: Mapping[int, TurnAnalysis],
    searched: Mapping[int, TurnAnalysis],
    number: int,
) -> MoveMetrics:
    color, move = request.moves[number - 1]
    before, after = turns.get(number - 1), turns.get(number)
    best = before.candidates[0].move if before is not None and before.candidates else None
    return MoveMetrics(
        move_number=number,
        color=color,
        move=move,
        best_move=best,
        sequential=_sequential(color, before, after),
        same_root=_same_root(
            color, move, before, searched.get(number - 1), min(LOW_VISITS, request.max_visits)
        ),
    )


def _sequential(
    color: Color, before: TurnAnalysis | None, after: TurnAnalysis | None
) -> LossEstimate:
    score = _difference(_root_score(color, before), _root_score(color, after))
    winrate = _difference(_root_winrate(color, after), _root_winrate(color, before))
    return _estimate(SEQUENTIAL, score, winrate)


def _same_root(
    color: Color,
    move: Move,
    before: TurnAnalysis | None,
    restricted: TurnAnalysis | None,
    enough_visits: int,
) -> LossEstimate:
    if before is None or not before.candidates:
        return _estimate(SAME_ROOT, None, None)
    best = before.candidates[0]
    flags: list[str] = []
    if restricted is not None:
        played = _candidate(restricted, move)
        flags.append(SEPARATE_SEARCH)
    else:
        played = _candidate(before, move)
    if played is None:
        if restricted is None:
            flags.append(NOT_SEARCHED)
        return _estimate(SAME_ROOT, None, None, *flags)
    if any(c.visits is None or c.visits < enough_visits for c in (best, played)):
        flags.append(LOW_VISITS_FLAG)
    score = _difference(_score(color, best), _score(color, played))
    winrate = _difference(_winrate(color, played), _winrate(color, best))
    return _estimate(SAME_ROOT, score, winrate, *flags)


def _candidate(analysis: TurnAnalysis, move: Move) -> Candidate | None:
    return next((c for c in analysis.candidates if c.move == move), None)


def _estimate(
    definition: str, score: float | None, winrate: float | None, *extra: str
) -> LossEstimate:
    flags = set(extra)
    if score is None:
        flags.add(MISSING_SCORE)
    elif score < 0:
        flags.add(NEGATIVE_NOISE)
    if winrate is None:
        flags.add(MISSING_WINRATE)
    return LossEstimate(
        definition=definition,
        raw_score_loss=score,
        winrate_delta_pp=None if winrate is None else winrate * 100,
        flags=tuple(sorted(flags)),
    )


def _difference(minuend: float | None, subtrahend: float | None) -> float | None:
    if minuend is None or subtrahend is None:
        return None
    value = minuend - subtrahend
    if not math.isfinite(value):
        # Two finite inputs can still overflow; such a value must not reach a report.
        raise MetricInputError("non_finite_difference", "a difference of evaluations overflows")
    return value


def _root_score(color: Color, analysis: TurnAnalysis | None) -> float | None:
    return None if analysis is None else score_for(color, analysis.root.score_lead_black)


def _root_winrate(color: Color, analysis: TurnAnalysis | None) -> float | None:
    return None if analysis is None else winrate_for(color, analysis.root.winrate_black)


def _score(color: Color, candidate: Candidate) -> float | None:
    return score_for(color, candidate.score_lead_black)


def _winrate(color: Color, candidate: Candidate) -> float | None:
    return winrate_for(color, candidate.winrate_black)
