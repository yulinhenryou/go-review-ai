"""Strict parsing of one KataGo analysis response (MIGRATION E01).

Values stay in BLACK perspective, as the engine is told to report them
(`reportAnalysisWinratesAs=BLACK`); `winrate_for` and `score_for` are the one
place they are turned to a player's perspective. A value the engine did not
report stays `None`: `utility` is never read, and no default such as a 50%
winrate or a zero score is ever filled in. Anything malformed raises
`EngineProtocolError` with a stable code instead of being repaired.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import weiqi_core

from weiqi.engine.errors import EngineProtocolError

if TYPE_CHECKING:
    from weiqi_core import Color, Move

    from weiqi.engine.request import AnalysisRequest


@dataclass(frozen=True, slots=True)
class Candidate:
    """One move the search considered, with its principal variation."""

    move: Move
    order: int
    """KataGo's ranking: 0 is the move it recommends."""
    visits: int | None
    winrate_black: float | None
    score_lead_black: float | None
    prior: float | None
    pv: tuple[Move, ...]
    """Starts with `move`; may be empty."""


@dataclass(frozen=True, slots=True)
class RootInfo:
    """Statistics for the analysed position itself."""

    current_player: Color
    visits: int | None
    winrate_black: float | None
    score_lead_black: float | None


@dataclass(frozen=True, slots=True)
class TurnAnalysis:
    """The final search result for one turn of a request."""

    turn: int
    root: RootInfo
    candidates: tuple[Candidate, ...]
    """Sorted by `order`, so `candidates[0]` is the recommendation."""
    ownership_black: tuple[float, ...] | None
    """Row-major from the top-left point, in [-1, 1]; `None` unless requested."""


def winrate_for(player: Color, winrate_black: float | None) -> float | None:
    """A BLACK-perspective winrate seen by `player`."""
    if winrate_black is None:
        return None
    return winrate_black if player == "B" else 1.0 - winrate_black


def score_for(player: Color, score_black: float | None) -> float | None:
    """A BLACK-perspective score lead seen by `player`."""
    if score_black is None:
        return None
    return score_black if player == "B" else -score_black


def _number(value: object, name: str, low: float = -math.inf, high: float = math.inf) -> float:
    # bool is an int subclass, and an int too large for a float overflows.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EngineProtocolError("invalid_number", f"{name} is not a number")
    try:
        number = float(value)
    except OverflowError:
        raise EngineProtocolError("invalid_number", f"{name} is out of range") from None
    if not math.isfinite(number):
        raise EngineProtocolError("invalid_number", f"{name} is not finite")
    if not low <= number <= high:
        raise EngineProtocolError("number_out_of_range", f"{name} is outside [{low}, {high}]")
    return number


def _optional_number(
    data: Mapping[str, object], name: str, low: float = -math.inf, high: float = math.inf
) -> float | None:
    value = data.get(name)
    return None if value is None else _number(value, name, low, high)


def _optional_visits(data: Mapping[str, object]) -> int | None:
    value = data.get("visits")
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise EngineProtocolError("invalid_visits", "visits must be a non-negative integer")
    return value


def _move(vertex: object, request: AnalysisRequest) -> Move:
    if not isinstance(vertex, str):
        raise EngineProtocolError("invalid_coordinate", "a move must be a GTP vertex string")
    try:
        return weiqi_core.from_gtp(vertex, request.width, request.height)
    except weiqi_core.CoreError as error:
        raise EngineProtocolError("invalid_coordinate", str(error)) from error


def parse_candidate(info: Mapping[str, object], request: AnalysisRequest, order: int) -> Candidate:
    """One `moveInfos` entry whose `order` `parse_turn` has already checked."""
    move = _move(info.get("move"), request)
    raw_pv = info.get("pv")
    if raw_pv is not None and not isinstance(raw_pv, list):
        raise EngineProtocolError("invalid_pv", "pv must be a list")
    pv = tuple(_move(vertex, request) for vertex in raw_pv or ())
    if pv and pv[0] != move:
        raise EngineProtocolError("pv_mismatch", "pv does not start with its candidate move")
    return Candidate(
        move=move,
        order=order,
        visits=_optional_visits(info),
        winrate_black=_optional_number(info, "winrate", 0.0, 1.0),
        score_lead_black=_optional_number(info, "scoreLead"),
        prior=_optional_number(info, "prior", 0.0, 1.0),
        pv=pv,
    )


def _ownership(payload: Mapping[str, object], request: AnalysisRequest) -> tuple[float, ...] | None:
    raw = payload.get("ownership")
    if raw is None:
        return None
    if not request.include_ownership:
        raise EngineProtocolError("unexpected_ownership", "ownership was not requested")
    if not isinstance(raw, list) or len(raw) != request.width * request.height:
        raise EngineProtocolError("invalid_ownership", "ownership must have one value per point")
    return tuple(_number(value, "ownership", -1.0, 1.0) for value in raw)


def parse_turn(payload: Mapping[str, object], request: AnalysisRequest, turn: int) -> TurnAnalysis:
    """The analysis of `turn` from one final (not during-search) response.

    Routing by query id and the final-result check belong to the process
    layer; this checks that the content fits the request.
    """
    if turn not in request.analyze_turns:
        raise EngineProtocolError("unexpected_turn", f"turn {turn} was not requested")
    root = payload.get("rootInfo")
    if not isinstance(root, Mapping):
        raise EngineProtocolError("missing_root_info", "the response has no rootInfo")
    if root.get("currentPlayer") != request.players[turn]:
        raise EngineProtocolError(
            "root_player_mismatch", "the engine analysed a different player than the request"
        )
    infos = payload.get("moveInfos")
    if not isinstance(infos, list) or not all(isinstance(info, Mapping) for info in infos):
        raise EngineProtocolError("invalid_move_infos", "moveInfos must be a list of objects")
    entries: Sequence[Mapping[str, object]] = infos
    orders: list[int] = []
    for entry in entries:
        order = entry.get("order")
        if type(order) is not int or order < 0:
            raise EngineProtocolError("invalid_order", "order must be a non-negative integer")
        orders.append(order)
    # The ranking must start at 0 with no repeats; array order is not ranking.
    if len(set(orders)) != len(orders) or (orders and min(orders) != 0):
        raise EngineProtocolError("invalid_order", "candidate orders must be distinct from 0")
    candidates = tuple(
        sorted(
            (
                parse_candidate(entry, request, order)
                for entry, order in zip(entries, orders, strict=True)
            ),
            key=lambda c: c.order,
        )
    )
    if len({c.move for c in candidates}) != len(candidates):
        raise EngineProtocolError("duplicate_candidate", "a move appears twice in moveInfos")
    current_player = request.players[turn]
    return TurnAnalysis(
        turn=turn,
        root=RootInfo(
            current_player=current_player,
            visits=_optional_visits(root),
            winrate_black=_optional_number(root, "winrate", 0.0, 1.0),
            score_lead_black=_optional_number(root, "scoreLead"),
        ),
        candidates=candidates,
        ownership_black=_ownership(payload, request),
    )
