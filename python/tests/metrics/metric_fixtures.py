"""Fixed evidence for metric tests: hand-built engine results whose values are
chosen by the test, bound to a real request and identity so the context
checks pass. Test doubles only; they say nothing about real search."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from weiqi.engine import (
    AnalysisRequest,
    Candidate,
    EngineIdentity,
    RootInfo,
    TurnAnalysis,
    TurnResult,
)
from weiqi.metrics import LossEstimate, MoveMetrics

if TYPE_CHECKING:
    from weiqi_core import Color, Move

IDENTITY = EngineIdentity(
    version="1.18.2",
    model_name="fixture-model",
    model_sha256="a" * 64,
    config_sha256="b" * 64,
    overrides=(("reportAnalysisWinratesAs", "BLACK"),),
)

# (score lead, winrate) in BLACK perspective; None for "not reported".
type Values = tuple[float | None, float | None]


@dataclass(frozen=True, slots=True)
class Evaluated:
    """Satisfies `weiqi.metrics.Evaluations`."""

    request: AnalysisRequest
    identity: EngineIdentity
    results: tuple[TurnResult, ...]


def moves(count: int) -> tuple[tuple[Color, Move], ...]:
    """Legal alternating moves on rows 0, 2, 4, ... so nothing is captured."""
    colors: tuple[Color, Color] = ("B", "W")
    return tuple((colors[i % 2], (i % 19, 2 * (i // 19))) for i in range(count))


def request(played: Sequence[tuple[Color, Move]]) -> AnalysisRequest:
    return AnalysisRequest(
        width=19,
        height=19,
        rules="chinese",
        komi=7.5,
        moves=tuple(played),
        analyze_turns=tuple(range(len(played) + 1)),
        max_visits=100,
    )


def candidate(move: Move, order: int, values: Values, visits: int | None = 50) -> Candidate:
    return Candidate(
        move=move,
        order=order,
        visits=visits,
        winrate_black=values[1],
        score_lead_black=values[0],
        prior=0.1,
        pv=(move,),
    )


def turn(
    req: AnalysisRequest,
    number: int,
    root: Values,
    candidates: Sequence[tuple[Move, Values]] = (),
) -> TurnResult:
    analysis = TurnAnalysis(
        turn=number,
        root=RootInfo(
            current_player=req.players[number],
            visits=100,
            winrate_black=root[1],
            score_lead_black=root[0],
        ),
        candidates=tuple(candidate(m, i, v) for i, (m, v) in enumerate(candidates)),
        ownership_black=None,
    )
    return TurnResult(analysis, req.query_key(IDENTITY, number), ())


def evaluated(req: AnalysisRequest, results: Sequence[TurnResult]) -> Evaluated:
    return Evaluated(req, IDENTITY, tuple(results))


def played_search(req: AnalysisRequest, number: int, values: Values) -> Evaluated:
    """The restricted search of the move played at `number`, giving it `values`."""
    restricted = req.played_move_search(number)
    move = req.moves[number][1]
    return evaluated(restricted, [turn(restricted, number, values, [(move, values)])])


def estimate(raw: float | None, definition: str = "score_loss.sequential.v1") -> LossEstimate:
    return LossEstimate(definition, raw, None, ())


def metrics(number: int, loss: float | None, same_root: float | None = None) -> MoveMetrics:
    """A move whose sequential (and optionally same-root) raw loss is given."""
    return MoveMetrics(
        move_number=number,
        color="B" if number % 2 else "W",
        move=(number % 19, 0),
        best_move=None,
        sequential=estimate(loss),
        same_root=estimate(same_root, "score_loss.same_root.v1"),
    )
