from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from src.analyzer import MoveAnalysisResult
from src.classifier import ClassifiedMistake, MistakeCategory
from src.katago_client import CandidateMove, PositionAnalysis
from src.mistake_severity import MistakeSeverity
from src.sgf_parser import ParsedGame
from src.user_facing_labels import (
    category_interpretation,
    category_label,
    category_training_suggestion,
    ordered_categories,
    severity_label,
)


@dataclass(frozen=True)
class CoordinateView:
    sgf: str | None
    display: str


@dataclass(frozen=True)
class CandidateView:
    move: CoordinateView
    score_estimate: float
    winrate: float


@dataclass(frozen=True)
class GameSummaryResult:
    board_size: int
    komi: float | None
    players: dict[str, str]
    result: str
    moves_analyzed: int
    mistakes_reviewed: int


@dataclass(frozen=True)
class SelectedMistakeResult:
    move_number: int
    color: str
    played_move: CoordinateView
    recommended_move: CoordinateView
    score_loss: float
    estimated_loss: float
    winrate_delta: float
    category: MistakeCategory
    category_label: str
    severity: MistakeSeverity
    severity_label: str
    pv_summary: str
    top_candidates: list[CandidateView]


@dataclass(frozen=True)
class ClassificationTotal:
    category: MistakeCategory
    label: str
    count: int


@dataclass(frozen=True)
class ClassificationResult:
    move_number: int
    category: MistakeCategory
    label: str


@dataclass(frozen=True)
class ClassificationsSummary:
    by_move: list[ClassificationResult]
    totals: list[ClassificationTotal]


@dataclass(frozen=True)
class ExplanationResult:
    move_number: int
    category: MistakeCategory
    title: str
    summary: str
    why_this_matters: str


@dataclass(frozen=True)
class TrainingSuggestion:
    category: MistakeCategory | None
    suggestion: str


@dataclass(frozen=True)
class CurrentPositionResult:
    next_player: str
    best_move: CoordinateView
    top_candidates: list[CandidateView]
    pv_summary: str
    score_estimate: float
    winrate: float


@dataclass(frozen=True)
class TimelineItemResult:
    move_number: int
    color: str
    played_move: CoordinateView
    best_move: CoordinateView
    score_loss: float
    winrate_delta: float
    score_before: float
    score_after: float
    winrate_before: float
    winrate_after: float
    category: MistakeCategory
    category_label: str
    severity: MistakeSeverity
    severity_label: str
    is_mistake: bool


@dataclass(frozen=True)
class ReviewSectionResult:
    mistakes_above_threshold: list[SelectedMistakeResult]
    classification_totals: list[ClassificationTotal]
    training_suggestions: list[TrainingSuggestion]


@dataclass(frozen=True)
class ReviewResult:
    schema_version: str
    game_summary: GameSummaryResult
    current_position: CurrentPositionResult
    timeline: list[TimelineItemResult]
    review: ReviewSectionResult
    selected_mistakes: list[SelectedMistakeResult]
    classifications: ClassificationsSummary
    explanations: list[ExplanationResult]
    training_suggestions: list[TrainingSuggestion]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_review_result(
    game: ParsedGame,
    selected_mistakes: list[ClassifiedMistake],
    threshold_mistakes: list[ClassifiedMistake],
    all_classified: list[ClassifiedMistake],
    results: list[MoveAnalysisResult],
    current_position_analysis: PositionAnalysis,
    next_player: str,
    loss_threshold: float,
) -> ReviewResult:
    by_move = {result.move_number: result for result in results}

    selected_views = [
        _selected_mistake_view(game.board_size, mistake, by_move[mistake.move_number])
        for mistake in selected_mistakes
    ]
    threshold_views = [
        _selected_mistake_view(game.board_size, mistake, by_move[mistake.move_number])
        for mistake in threshold_mistakes
    ]
    selected_classifications = _classifications_summary(selected_mistakes)
    threshold_totals = _classification_totals(threshold_mistakes)
    selected_training = _training_suggestions(selected_mistakes)
    threshold_training = _training_suggestions(threshold_mistakes)

    return ReviewResult(
        schema_version="2.0",
        game_summary=GameSummaryResult(
            board_size=game.board_size,
            komi=game.komi,
            players={
                "black": game.black_player or "Unknown Black",
                "white": game.white_player or "Unknown White",
            },
            result=game.result or "unknown",
            moves_analyzed=len(game.moves),
            mistakes_reviewed=len(selected_mistakes),
        ),
        current_position=_current_position_view(
            board_size=game.board_size,
            next_player=next_player,
            analysis=current_position_analysis,
        ),
        timeline=[
            _timeline_item(
                board_size=game.board_size,
                result=result,
                classified=all_classified[result.move_number - 1],
                loss_threshold=loss_threshold,
            )
            for result in results
        ],
        review=ReviewSectionResult(
            mistakes_above_threshold=threshold_views,
            classification_totals=threshold_totals,
            training_suggestions=threshold_training,
        ),
        selected_mistakes=selected_views,
        classifications=selected_classifications,
        explanations=[
            _explanation(game.board_size, item)
            for item in selected_views
        ],
        training_suggestions=selected_training,
    )


def review_result_to_dict(review: ReviewResult) -> dict[str, Any]:
    return review.to_dict()


def _current_position_view(
    board_size: int,
    next_player: str,
    analysis: PositionAnalysis,
) -> CurrentPositionResult:
    return CurrentPositionResult(
        next_player=next_player,
        best_move=_coord_view(analysis.best_move, board_size),
        top_candidates=[
            _candidate_view(candidate, board_size)
            for candidate in analysis.top_candidates
        ],
        pv_summary=analysis.pv_summary,
        score_estimate=analysis.score_estimate,
        winrate=analysis.winrate,
    )


def _selected_mistake_view(
    board_size: int,
    mistake: ClassifiedMistake,
    result: MoveAnalysisResult,
) -> SelectedMistakeResult:
    return SelectedMistakeResult(
        move_number=mistake.move_number,
        color=result.color,
        played_move=_coord_view(mistake.played_move, board_size),
        recommended_move=_coord_view(mistake.recommended_move, board_size),
        score_loss=mistake.score_loss,
        estimated_loss=mistake.estimated_loss,
        winrate_delta=mistake.winrate_delta,
        category=mistake.category,
        category_label=category_label(mistake.category),
        severity=mistake.severity,
        severity_label=severity_label(mistake.severity),
        pv_summary=result.engine_analysis.pv_summary,
        top_candidates=[
            _candidate_view(candidate, board_size)
            for candidate in result.engine_analysis.top_candidates
        ],
    )


def _candidate_view(candidate: CandidateMove, board_size: int) -> CandidateView:
    return CandidateView(
        move=_coord_view(candidate.move, board_size),
        score_estimate=candidate.score_estimate,
        winrate=candidate.winrate,
    )


def _timeline_item(
    board_size: int,
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
    loss_threshold: float,
) -> TimelineItemResult:
    return TimelineItemResult(
        move_number=result.move_number,
        color=result.color,
        played_move=_coord_view(result.played_move, board_size),
        best_move=_coord_view(result.recommended_move, board_size),
        score_loss=result.estimated_loss,
        winrate_delta=round(
            result.engine_analysis.played_winrate - result.engine_analysis.winrate,
            2,
        ),
        score_before=result.engine_analysis.score_estimate,
        score_after=result.engine_analysis.played_score_estimate,
        winrate_before=result.engine_analysis.winrate,
        winrate_after=result.engine_analysis.played_winrate,
        category=classified.category,
        category_label=category_label(classified.category),
        severity=classified.severity,
        severity_label=severity_label(classified.severity),
        is_mistake=result.estimated_loss >= loss_threshold,
    )


def _classifications_summary(mistakes: list[ClassifiedMistake]) -> ClassificationsSummary:
    return ClassificationsSummary(
        by_move=[
            ClassificationResult(
                move_number=item.move_number,
                category=item.category,
                label=category_label(item.category),
            )
            for item in mistakes
        ],
        totals=_classification_totals(mistakes),
    )


def _classification_totals(mistakes: list[ClassifiedMistake]) -> list[ClassificationTotal]:
    counts = Counter(mistake.category for mistake in mistakes)
    return [
        ClassificationTotal(
            category=category,
            label=category_label(category),
            count=counts[category],
        )
        for category in ordered_categories()
        if counts[category] > 0
    ]


def _explanation(board_size: int, mistake: SelectedMistakeResult) -> ExplanationResult:
    played = mistake.played_move.display
    recommended = mistake.recommended_move.display
    label = category_label(mistake.category)
    return ExplanationResult(
        move_number=mistake.move_number,
        category=mistake.category,
        title=f"Move {mistake.move_number} ({label})",
        summary=(
            f"You played {played}; KataGo prefers {recommended} "
            f"(loss {mistake.estimated_loss:.2f})."
        ),
        why_this_matters=category_interpretation(mistake.category),
    )


def _training_suggestions(mistakes: list[ClassifiedMistake]) -> list[TrainingSuggestion]:
    if not mistakes:
        return [
            TrainingSuggestion(
                category=None,
                suggestion="Keep playing and collect more reviewed games.",
            )
        ]

    counts = Counter(item.category for item in mistakes)
    suggestions = [
        TrainingSuggestion(
            category=category,
            suggestion=category_training_suggestion(category),
        )
        for category, _count in counts.most_common(2)
    ]
    suggestions.append(
        TrainingSuggestion(
            category=None,
            suggestion="In your next review, compare your move with the best move before reading comments.",
        )
    )
    return suggestions


def _coord_view(move: str | None, board_size: int) -> CoordinateView:
    if move is None or move == "pass":
        return CoordinateView(sgf=None if move is None else move, display="pass")

    human = _sgf_to_human_coord(move, board_size)
    if human is None:
        return CoordinateView(sgf=move, display=move)
    return CoordinateView(sgf=move, display=human)


def _sgf_to_human_coord(move: str, board_size: int) -> str | None:
    if len(move) != 2 or board_size <= 0:
        return None

    x = ord(move[0]) - ord("a")
    y = ord(move[1]) - ord("a")
    if x < 0 or y < 0 or x >= board_size or y >= board_size:
        return None

    column = _go_column_label(x)
    row = board_size - y
    return f"{column}{row}"


def _go_column_label(index: int) -> str:
    label_index = index
    if index >= 8:
        label_index += 1
    return chr(ord("A") + label_index)
