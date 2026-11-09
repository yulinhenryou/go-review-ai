"""A fixed four-move game with hand-written evidence, shared by the review
result tests and the report tests."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from metric_fixtures import Evaluated, Values, evaluated, turn

from weiqi.engine import TurnResult
from weiqi.review import GameInput, ReviewResult, ReviewSettings, build_result, read_game
from weiqi.review import review_request as make_request

if TYPE_CHECKING:
    from weiqi_core import Move

SGF = b"(;FF[4]GM[1]SZ[19]RU[Chinese]KM[7.5]PB[Alice]PW[Bob]RE[B+R];B[pd];W[dd];B[pp];W[])"
OTHER = (10, 10)
EMPTY = [0.0] * 361

# Black-perspective (score, winrate) per turn: B loses 5, W loses 9, B loses 1, W loses 4.
ROOTS: list[Values | None] = [(0.0, 0.5), (-5.0, 0.3), (4.0, 0.7), (3.0, 0.65), (7.0, 0.8)]


def setup(
    roots: Sequence[Values | None],
    *,
    ownership: Sequence[float] | None = EMPTY,
    played_value: Values | None = None,
    warnings: dict[int, tuple[str, ...]] | None = None,
    sgf: bytes = SGF,
) -> tuple[GameInput, Evaluated]:
    """The fixed game with one root value per turn (`None`: not analysed).
    Each turn's candidates are OTHER (the recommendation, with the root
    value) and, if `played_value` is given, the played move."""
    game = read_game(sgf)
    req = make_request(game, "chinese", 7.5, max_visits=100)
    results: list[TurnResult] = []
    for number, root in enumerate(roots):
        if root is None:
            continue
        candidates: list[tuple[Move, Values]] = [(OTHER, root)]
        if played_value is not None and number < len(req.moves):
            candidates.append((req.moves[number][1], played_value))
        result = turn(req, number, root, candidates, ownership)
        if warnings and number in warnings:
            result = TurnResult(result.analysis, result.query_key, warnings[number])
        results.append(result)
    return game, evaluated(req, results)


def review(
    roots: Sequence[Values | None] = ROOTS,
    *,
    settings: ReviewSettings | None = None,
    ownership: Sequence[float] | None = EMPTY,
    warnings: dict[int, tuple[str, ...]] | None = None,
    sgf: bytes = SGF,
) -> ReviewResult:
    game, evaluations = setup(roots, ownership=ownership, warnings=warnings, sgf=sgf)
    return build_result(game, evaluations, [], settings or ReviewSettings())
