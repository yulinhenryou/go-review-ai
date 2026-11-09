"""The single-game review result, schema `review.v1` (MIGRATION R06).

It keeps the prototype's concepts (coverage with partial vs complete, a
method block, the chronological timeline apart from the ranked mistakes,
Black-perspective chart values) and carries codes and numbers only: every
sentence is rendered later from a locale catalog (`weiqi.explain`).

`build_result` is a pure function of the evaluations, so the same evidence
always gives the same result; whether turns came from the cache or the
engine is recorded with the run, not here. Points are `(x, y)` from the top
left, as everywhere in the Python layer; moves are a point or "pass".
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Final, Literal

from weiqi.metrics import (
    DEFAULT_BAND,
    DEFAULT_BANDS,
    DEFAULT_CALIBRATION,
    DEFAULT_THRESHOLDS,
    GROUP_STATUS,
    SAME_ROOT,
    SEQUENTIAL,
    TURNING_POINTS,
    Evaluations,
    GroupStatusChange,
    MetricInputError,
    Severity,
    SeverityBand,
    StatusThresholds,
    TurningPoint,
    WinrateBands,
    move_metrics,
    ownership_facts,
    select_mistakes,
    turning_points,
)
from weiqi.metrics.evidence import evaluated_turns

if TYPE_CHECKING:
    from weiqi_core import Color, Move

    from weiqi.engine import TurnAnalysis
    from weiqi.review.game_input import GameInput, RecordStatus

RESULT_SCHEMA: Final = "review.v1"
RANKING: Final = "unrounded_loss_desc_then_move_number"


@dataclass(frozen=True, slots=True)
class ReviewSettings:
    """What a review may be asked to change; everything else is fixed by the
    versioned definitions."""

    max_visits: int = 200
    pv_length: int = 8
    band: SeverityBand = DEFAULT_BAND
    status_thresholds: StatusThresholds = DEFAULT_THRESHOLDS
    winrate_bands: WinrateBands = DEFAULT_BANDS
    mistake_limit: int | None = None
    """At most this many ranked mistakes; `None` lists every one."""

    def __post_init__(self) -> None:
        limit = self.mistake_limit
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise MetricInputError("invalid_limit", "mistake_limit must be a positive integer")


@dataclass(frozen=True, slots=True)
class GameSummary:
    width: int
    height: int
    rules: str
    komi: float
    handicap: int | None
    setup_black: int
    setup_white: int
    black_player: str | None
    white_player: str | None
    result_text: str | None
    record_status: RecordStatus
    sgf_sha256: str
    encoding: str
    input_warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EngineSummary:
    version: str
    model_name: str
    model_sha256: str
    config_sha256: str
    overrides: tuple[tuple[str, object], ...]
    max_visits: int
    pv_length: int


@dataclass(frozen=True, slots=True)
class Method:
    """Every definition and setting the numbers depend on (ADR-008, ADR-011)."""

    score_loss: str
    score_loss_diagnostic: str
    score_unit: str
    loss_perspective: str
    winrate_delta_unit: str
    chart_perspective: str
    severity_table: str
    severity_band: str
    mistake_threshold: float
    severe_threshold: float
    ranking: str
    mistake_limit: int | None
    group_status: str
    status_alive: float
    status_dead: float
    turning_points: str
    band_black_ahead: float
    band_white_ahead: float
    turning_point_min_drop_pp: float
    thresholds_calibrated: bool


@dataclass(frozen=True, slots=True)
class Coverage:
    moves_total: int
    moves_with_score: int
    missing_score_moves: tuple[int, ...]
    moves_with_winrate: int
    missing_winrate_moves: tuple[int, ...]
    moves_with_ownership: int
    missing_ownership_moves: tuple[int, ...]
    current_position_evaluated: bool
    played_move_searches: int


@dataclass(frozen=True, slots=True)
class MoveReview:
    """One move of the timeline. Loss values are the mover's; `*_black_*`
    values are root values in Black's perspective, for the chart."""

    move_number: int
    color: Color
    move: Move
    best_move: Move | None
    pv: tuple[Move, ...]
    """The recommendation's variation, from the search before the move."""
    score_loss: float | None
    raw_score_loss: float | None
    winrate_delta_pp: float | None
    severity: Severity | None
    flags: tuple[str, ...]
    same_root_score_loss: float | None
    same_root_raw_score_loss: float | None
    same_root_winrate_delta_pp: float | None
    same_root_flags: tuple[str, ...]
    score_black_before: float | None
    score_black_after: float | None
    winrate_black_before: float | None
    winrate_black_after: float | None
    ownership_evaluated: bool
    group_changes: tuple[GroupStatusChange, ...]


@dataclass(frozen=True, slots=True)
class RankedMistake:
    move_number: int
    color: Color
    score_loss: float
    severity: Severity


@dataclass(frozen=True, slots=True)
class CandidateView:
    move: Move
    visits: int | None
    score_black: float | None
    winrate_black: float | None
    pv: tuple[Move, ...]


@dataclass(frozen=True, slots=True)
class CurrentPosition:
    """The position after the last recorded move."""

    turn: int
    to_play: Color
    evaluated: bool
    score_black: float | None
    winrate_black: float | None
    best_move: Move | None
    candidates: tuple[CandidateView, ...]


@dataclass(frozen=True, slots=True)
class ReviewResult:
    schema: str
    status: Literal["complete", "partial"]
    game: GameSummary
    engine: EngineSummary
    method: Method
    coverage: Coverage
    timeline: tuple[MoveReview, ...]
    mistakes: tuple[RankedMistake, ...]
    turning_points: tuple[TurningPoint, ...]
    current_position: CurrentPosition
    warnings: tuple[str, ...]
    """Codes about the primary evidence: sequential flags, engine warnings and
    the final position, sorted."""
    diagnostic_warnings: tuple[str, ...]
    """Same-root flags, sorted. They concern only the diagnostic values, so a
    report must not present them as gaps in the primary evidence."""

    def to_json(self) -> str:
        """Canonical JSON: sorted keys, no NaN, tuples as arrays."""
        return json.dumps(asdict(self), sort_keys=True, allow_nan=False, ensure_ascii=False)


def build_result(
    game: GameInput,
    evaluations: Evaluations,
    played_searches: Sequence[Evaluations],
    settings: ReviewSettings,
) -> ReviewResult:
    """The review of `game` from its whole-game evaluations and the
    restricted searches of its played moves."""
    request, identity = evaluations.request, evaluations.identity
    turns = evaluated_turns(evaluations)
    metrics = move_metrics(evaluations, played_searches)
    facts = ownership_facts(evaluations, settings.status_thresholds)
    ranked = select_mistakes(metrics, settings.band, limit=settings.mistake_limit)
    every_mistake = {
        m.metrics.move_number: m.severity for m in select_mistakes(metrics, settings.band)
    }

    timeline = []
    for item, fact in zip(metrics, facts, strict=True):
        before, after = turns.get(item.move_number - 1), turns.get(item.move_number)
        timeline.append(
            MoveReview(
                move_number=item.move_number,
                color=item.color,
                move=item.move,
                best_move=item.best_move,
                pv=before.candidates[0].pv if before is not None and before.candidates else (),
                score_loss=item.sequential.score_loss,
                raw_score_loss=item.sequential.raw_score_loss,
                winrate_delta_pp=item.sequential.winrate_delta_pp,
                severity=every_mistake.get(item.move_number),
                flags=item.sequential.flags,
                same_root_score_loss=item.same_root.score_loss,
                same_root_raw_score_loss=item.same_root.raw_score_loss,
                same_root_winrate_delta_pp=item.same_root.winrate_delta_pp,
                same_root_flags=item.same_root.flags,
                score_black_before=_root(before, "score"),
                score_black_after=_root(after, "score"),
                winrate_black_before=_root(before, "winrate"),
                winrate_black_after=_root(after, "winrate"),
                ownership_evaluated=fact.ownership_delta is not None,
                group_changes=fact.group_changes,
            )
        )

    current = _current(turns.get(len(request.moves)), len(request.moves), request.players[-1])
    coverage = Coverage(
        moves_total=len(timeline),
        moves_with_score=sum(m.raw_score_loss is not None for m in timeline),
        missing_score_moves=tuple(m.move_number for m in timeline if m.raw_score_loss is None),
        moves_with_winrate=sum(m.winrate_delta_pp is not None for m in timeline),
        missing_winrate_moves=tuple(m.move_number for m in timeline if m.winrate_delta_pp is None),
        moves_with_ownership=sum(m.ownership_evaluated for m in timeline),
        missing_ownership_moves=tuple(m.move_number for m in timeline if not m.ownership_evaluated),
        current_position_evaluated=current.evaluated,
        played_move_searches=len(played_searches),
    )
    complete = (
        not coverage.missing_score_moves
        and not coverage.missing_winrate_moves
        and not coverage.missing_ownership_moves
        and coverage.current_position_evaluated
    )
    record = game.record
    info = record.info
    return ReviewResult(
        schema=RESULT_SCHEMA,
        status="complete" if complete else "partial",
        game=GameSummary(
            width=request.width,
            height=request.height,
            rules=request.rules,
            komi=request.komi,
            handicap=record.handicap,
            setup_black=len(request.initial_black),
            setup_white=len(request.initial_white),
            black_player=info.black_player,
            white_player=info.white_player,
            result_text=info.result_text,
            record_status=game.record_status,
            sgf_sha256=game.sgf_sha256,
            encoding=game.encoding,
            input_warnings=game.input_warnings,
        ),
        engine=EngineSummary(
            version=identity.version,
            model_name=identity.model_name,
            model_sha256=identity.model_sha256,
            config_sha256=identity.config_sha256,
            overrides=identity.overrides,
            max_visits=request.max_visits,
            pv_length=request.pv_length,
        ),
        method=_method(settings),
        coverage=coverage,
        timeline=tuple(timeline),
        mistakes=tuple(
            RankedMistake(m.metrics.move_number, m.metrics.color, m.score_loss, m.severity)
            for m in ranked
        ),
        turning_points=turning_points(evaluations, settings.winrate_bands),
        current_position=current,
        warnings=_warnings(timeline, current, [evaluations, *played_searches]),
        diagnostic_warnings=tuple(sorted({f for m in timeline for f in m.same_root_flags})),
    )


def _root(analysis: TurnAnalysis | None, value: Literal["score", "winrate"]) -> float | None:
    if analysis is None:
        return None
    root = analysis.root
    return root.score_lead_black if value == "score" else root.winrate_black


def _current(analysis: TurnAnalysis | None, turn: int, to_play: Color) -> CurrentPosition:
    if analysis is None:
        return CurrentPosition(turn, to_play, False, None, None, None, ())
    root = analysis.root
    return CurrentPosition(
        turn=turn,
        to_play=to_play,
        evaluated=root.score_lead_black is not None and root.winrate_black is not None,
        score_black=root.score_lead_black,
        winrate_black=root.winrate_black,
        best_move=analysis.candidates[0].move if analysis.candidates else None,
        candidates=tuple(
            CandidateView(c.move, c.visits, c.score_lead_black, c.winrate_black, c.pv)
            for c in analysis.candidates
        ),
    )


def _method(settings: ReviewSettings) -> Method:
    return Method(
        score_loss=SEQUENTIAL,
        score_loss_diagnostic=SAME_ROOT,
        score_unit="points",
        loss_perspective="mover",
        winrate_delta_unit="percentage_points",
        chart_perspective="BLACK",
        severity_table=DEFAULT_CALIBRATION.version,
        severity_band=settings.band.name,
        mistake_threshold=settings.band.mistake,
        severe_threshold=settings.band.severe,
        ranking=RANKING,
        mistake_limit=settings.mistake_limit,
        group_status=GROUP_STATUS,
        status_alive=settings.status_thresholds.alive,
        status_dead=settings.status_thresholds.dead,
        turning_points=TURNING_POINTS,
        band_black_ahead=settings.winrate_bands.black_ahead,
        band_white_ahead=settings.winrate_bands.white_ahead,
        turning_point_min_drop_pp=settings.winrate_bands.min_drop_pp,
        thresholds_calibrated=False,
    )


def _warnings(
    timeline: Iterable[MoveReview], current: CurrentPosition, sources: Iterable[Evaluations]
) -> tuple[str, ...]:
    codes = {flag for m in timeline for flag in m.flags}
    codes |= {w for source in sources for r in source.results for w in r.engine_warnings}
    if not current.evaluated:
        codes.add("missing_current_value")
    if current.evaluated and current.best_move is None:
        codes.add("no_candidate_moves")
    return tuple(sorted(codes))
