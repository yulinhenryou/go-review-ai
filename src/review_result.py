from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.analyzer import GameAnalysis, MoveAnalysisResult
from src.engine_types import AnalysisEvidence, CandidateMove, PositionAnalysis, PVMove
from src.mistake_selector import assess_move, select_top_mistakes
from src.mistake_severity import MistakeSeverity, severity_from_loss, severity_label
from src.report_writer import current_summary, move_summary, quality_notes, review_summary
from src.sgf_parser import ParsedGame


@dataclass(frozen=True)
class CoordinateView:
    sgf: str | None
    display: str


@dataclass(frozen=True)
class CandidateView:
    move: CoordinateView
    score_estimate: float | None
    winrate: float | None
    pv: tuple[PVMove, ...]
    visits: int | None
    score_black: float | None
    winrate_black: float | None


@dataclass(frozen=True)
class GameSummaryResult:
    board_size: int
    rules: str
    record_status: str
    input_warnings: tuple[str, ...]
    komi: float
    players: dict[str, str]
    result: str | None
    moves_analyzed: int
    mistakes_reviewed: int


@dataclass(frozen=True)
class CoverageResult:
    moves_total: int
    moves_evaluated: int
    missing_move_numbers: tuple[int, ...]
    moves_with_winrate: int
    missing_winrate_move_numbers: tuple[int, ...]
    current_position_evaluated: bool


@dataclass(frozen=True)
class ReviewMethod:
    loss_threshold: float
    severe_threshold: float
    top_limit: int
    score_unit: str = "points"
    loss_perspective: str = "moving_player"
    winrate_delta_unit: str = "percentage_points"
    winrate_delta_definition: str = "played_minus_recommended"
    chart_perspective: str = "BLACK"
    ranking: str = "unrounded_loss_desc_then_move_number"
    note: str = "阈值是可调整的产品设置，尚待校准；分析数值为搜索估计，不代表确定结论。"


@dataclass(frozen=True)
class MoveReviewResult:
    move_number: int
    color: str
    played_move: CoordinateView
    recommended_move: CoordinateView | None
    score_loss: float | None
    raw_score_loss: float | None
    winrate_delta_pp: float | None
    score_before: float | None
    score_after: float | None
    winrate_before: float | None
    winrate_after: float | None
    score_black_before: float | None
    score_black_after: float | None
    winrate_black_before: float | None
    winrate_black_after: float | None
    severity: MistakeSeverity | None
    severity_label: str | None
    is_mistake: bool | None
    status: str
    pv: tuple[PVMove, ...]
    pv_summary: str
    top_candidates: list[CandidateView]
    played_candidate: CandidateView | None
    evidence: AnalysisEvidence | None
    warnings: tuple[str, ...]
    quality_notes: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class CurrentPositionResult:
    next_player: str
    best_move: CoordinateView | None
    top_candidates: list[CandidateView]
    pv_summary: str
    score_estimate: float | None
    winrate: float | None
    short_explanation: str
    evidence: AnalysisEvidence | None
    warnings: tuple[str, ...]
    quality_notes: tuple[str, ...]


@dataclass(frozen=True)
class ReviewSectionResult:
    # All qualifying moves in chronology, independent of the top-five ranking.
    mistakes_above_threshold: list[MoveReviewResult]


@dataclass(frozen=True)
class ReviewResult:
    schema_version: str
    engine_source: str
    status: str
    summary: str
    game_summary: GameSummaryResult
    coverage: CoverageResult
    method: ReviewMethod
    current_position: CurrentPositionResult
    timeline: list[MoveReviewResult]
    review: ReviewSectionResult
    selected_mistakes: list[MoveReviewResult]
    warnings: tuple[str, ...]
    quality_notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_review_result(
    game: ParsedGame, analysis: GameAnalysis, loss_threshold: float,
    severe_threshold: float, limit: int,
) -> ReviewResult:
    timeline = [_move_view(game.board_size, item, loss_threshold, severe_threshold) for item in analysis.move_results]
    by_move = {item.move_number: item for item in timeline}
    selected = [by_move[item.move_number] for item in select_top_mistakes(
        analysis.move_results, loss_threshold, limit, severe_threshold,
    )]
    all_mistakes = [item for item in timeline if item.is_mistake]
    current = _current_view(game.board_size, analysis.current_position, analysis.current_position_input.to_play)
    missing = tuple(item.move_number for item in timeline if item.score_loss is None)
    missing_winrate = tuple(item.move_number for item in timeline if item.winrate_delta_pp is None)
    current_evaluated = current.score_estimate is not None and current.winrate is not None
    coverage = CoverageResult(len(timeline), len(timeline) - len(missing), missing,
                              len(timeline) - len(missing_winrate), missing_winrate, current_evaluated)
    status = "partial" if missing or missing_winrate or not current_evaluated else "complete"
    warnings = tuple(sorted({warning for item in timeline for warning in item.warnings} | set(current.warnings)))
    return ReviewResult(
        schema_version="3.0",
        engine_source="katago" if all(item.evidence is not None for item in [*timeline, current]) else "unverified_test_double",
        status=status,
        summary=review_summary(coverage, len(all_mistakes), status),
        game_summary=GameSummaryResult(
            game.board_size, game.rules, game.record_status, game.warnings, game.komi,
            {"black": game.black_player or "未知", "white": game.white_player or "未知"},
            game.result, len(timeline), len(selected),
        ),
        coverage=coverage, method=ReviewMethod(loss_threshold, severe_threshold, limit),
        current_position=current, timeline=timeline, review=ReviewSectionResult(all_mistakes),
        selected_mistakes=selected, warnings=warnings, quality_notes=quality_notes(warnings),
    )


def _move_view(board_size: int, result: MoveAnalysisResult, threshold: float, severe: float) -> MoveReviewResult:
    value = result.engine_analysis
    assessment = assess_move(result)
    severity = severity_from_loss(assessment.score_loss, threshold, severe)
    played = _coord_view(result.played_move, board_size)
    recommended = _coord_view(value.best_move, board_size) if value.best_move is not None else None
    pv = _recommendation_pv(value)
    warnings = tuple(sorted(set(assessment.warnings) | ({"missing_pv"} if not pv else set())))
    sign = 1 if result.color == "B" else -1
    return MoveReviewResult(
        move_number=result.move_number, color=result.color, played_move=played, recommended_move=recommended,
        score_loss=assessment.score_loss, raw_score_loss=assessment.raw_score_loss,
        winrate_delta_pp=assessment.winrate_delta_pp,
        score_before=value.score_estimate, score_after=value.played_score_estimate,
        winrate_before=value.winrate, winrate_after=value.played_winrate,
        score_black_before=value.score_estimate * sign if value.score_estimate is not None else None,
        score_black_after=value.played_score_estimate * sign if value.played_score_estimate is not None else None,
        winrate_black_before=_black_winrate(value.winrate, result.color),
        winrate_black_after=_black_winrate(value.played_winrate, result.color),
        severity=severity, severity_label=severity_label(severity),
        is_mistake=severity is not None if assessment.score_loss is not None else None,
        status="unavailable" if assessment.score_loss is None else "evaluated",
        pv=pv, pv_summary=_pv_summary(pv, board_size),
        top_candidates=[_candidate_view(c, board_size) for c in value.top_candidates],
        played_candidate=_candidate_view(value.played_candidate, board_size) if value.played_candidate else None,
        evidence=value.evidence, warnings=warnings, quality_notes=quality_notes(warnings),
        summary=move_summary(result.move_number, result.color, played.display,
                             recommended.display if recommended else None,
                             assessment.score_loss, assessment.winrate_delta_pp),
    )


def _current_view(board_size: int, value: PositionAnalysis, next_player: str) -> CurrentPositionResult:
    best = _coord_view(value.best_move, board_size) if value.best_move is not None else None
    warnings = set(value.evidence.warnings) if value.evidence else {"unverified_engine"}
    if value.score_estimate is None or value.winrate is None:
        warnings.add("missing_current_value")
    pv = _recommendation_pv(value)
    if not pv:
        warnings.add("missing_pv")
    return CurrentPositionResult(
        next_player, best, [_candidate_view(c, board_size) for c in value.top_candidates],
        _pv_summary(pv, board_size), value.score_estimate, value.winrate,
        current_summary(next_player, best.display if best else None, value.score_estimate, value.winrate),
        value.evidence, tuple(sorted(warnings)), quality_notes(warnings),
    )


def _recommendation_pv(value: PositionAnalysis) -> tuple[PVMove, ...]:
    return next((candidate.pv for candidate in value.top_candidates if candidate.move == value.best_move), ())


def _candidate_view(candidate: CandidateMove, board_size: int) -> CandidateView:
    return CandidateView(_coord_view(candidate.move, board_size), candidate.score_estimate,
                         candidate.winrate, candidate.pv, candidate.visits, candidate.score_black, candidate.winrate_black)


def _black_winrate(value: float | None, color: str) -> float | None:
    return None if value is None else value if color == "B" else 1 - value


def _pv_summary(pv: tuple[PVMove, ...], board_size: int) -> str:
    return " -> ".join(f"{'黑' if step.color == 'B' else '白'}{_coord_view(step.move, board_size).display}" for step in pv)


def _coord_view(move: str | None, board_size: int) -> CoordinateView:
    if move is None or move == "pass":
        return CoordinateView(move, "停一手")
    x, y = ord(move[0]) - ord("a"), ord(move[1]) - ord("a")
    return CoordinateView(move, f"{'ABCDEFGHJKLMNOPQRST'[x]}{board_size - y}")
