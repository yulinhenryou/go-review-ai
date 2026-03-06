from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from src.analyzer import MoveAnalysisResult
from src.classifier import ClassifiedMistake, MistakeCategory
from src.katago_client import CandidateMove
from src.sgf_parser import ParsedGame

_CATEGORY_LABELS: dict[MistakeCategory, str] = {
    "direction_error": "Direction error",
    "local_overplay": "Local overplay",
    "defensive_overreaction": "Defensive overreaction",
    "endgame_loss": "Endgame value loss",
    "tactical_blunder": "Tactical blunder",
    "unclear": "Unclear classification",
}

_CATEGORY_INTERPRETATION: dict[MistakeCategory, str] = {
    "direction_error": "This likely chose the wrong side or direction of play.",
    "local_overplay": "This likely pushed too hard in a local fight.",
    "defensive_overreaction": "This looks playable, but likely more cautious than needed.",
    "endgame_loss": "This likely missed available endgame points.",
    "tactical_blunder": "This likely missed a concrete tactical detail.",
    "unclear": "Engine signals are mixed, so this pattern is not yet clear.",
}

_CATEGORY_TRAINING: dict[MistakeCategory, str] = {
    "direction_error": "Review opening direction principles and compare side choices.",
    "local_overplay": "Practice choosing calmer local continuations in fighting positions.",
    "defensive_overreaction": "Review examples where active play is stronger than pure safety.",
    "endgame_loss": "Do short endgame counting drills before each game session.",
    "tactical_blunder": "Do a focused life-and-death and reading exercise set.",
    "unclear": "Recheck this position manually because the pattern is not conclusive.",
}

_CATEGORY_ORDER: tuple[MistakeCategory, ...] = (
    "direction_error",
    "local_overplay",
    "defensive_overreaction",
    "endgame_loss",
    "tactical_blunder",
    "unclear",
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
    estimated_loss: float
    category: MistakeCategory
    category_label: str
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
class ReviewResult:
    schema_version: str
    game_summary: GameSummaryResult
    selected_mistakes: list[SelectedMistakeResult]
    classifications: ClassificationsSummary
    explanations: list[ExplanationResult]
    training_suggestions: list[TrainingSuggestion]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_review_result(
    game: ParsedGame,
    mistakes: list[ClassifiedMistake],
    results: list[MoveAnalysisResult],
) -> ReviewResult:
    by_move = {result.move_number: result for result in results}

    selected_mistakes = [
        _selected_mistake_view(game.board_size, mistake, by_move[mistake.move_number])
        for mistake in mistakes
    ]
    classifications = _classifications_summary(mistakes)
    explanations = [
        _explanation(game.board_size, item)
        for item in selected_mistakes
    ]

    return ReviewResult(
        schema_version="1.0",
        game_summary=GameSummaryResult(
            board_size=game.board_size,
            komi=game.komi,
            players={
                "black": game.black_player or "Unknown Black",
                "white": game.white_player or "Unknown White",
            },
            result=game.result or "unknown",
            moves_analyzed=len(game.moves),
            mistakes_reviewed=len(mistakes),
        ),
        selected_mistakes=selected_mistakes,
        classifications=classifications,
        explanations=explanations,
        training_suggestions=_training_suggestions(mistakes),
    )


def review_result_to_dict(review: ReviewResult) -> dict[str, Any]:
    return review.to_dict()


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
        estimated_loss=mistake.estimated_loss,
        category=mistake.category,
        category_label=_CATEGORY_LABELS[mistake.category],
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


def _classifications_summary(mistakes: list[ClassifiedMistake]) -> ClassificationsSummary:
    counts = Counter(mistake.category for mistake in mistakes)
    return ClassificationsSummary(
        by_move=[
            ClassificationResult(
                move_number=item.move_number,
                category=item.category,
                label=_CATEGORY_LABELS[item.category],
            )
            for item in mistakes
        ],
        totals=[
            ClassificationTotal(
                category=category,
                label=_CATEGORY_LABELS[category],
                count=counts[category],
            )
            for category in _CATEGORY_ORDER
            if counts[category] > 0
        ],
    )


def _explanation(board_size: int, mistake: SelectedMistakeResult) -> ExplanationResult:
    played = mistake.played_move.display
    recommended = mistake.recommended_move.display
    label = _CATEGORY_LABELS[mistake.category]
    return ExplanationResult(
        move_number=mistake.move_number,
        category=mistake.category,
        title=f"Move {mistake.move_number} ({label})",
        summary=(
            f"You played {played}; KataGo prefers {recommended} "
            f"(loss {mistake.estimated_loss:.2f})."
        ),
        why_this_matters=_CATEGORY_INTERPRETATION[mistake.category],
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
            suggestion=_CATEGORY_TRAINING[category],
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
    if move is None:
        return CoordinateView(sgf=None, display="pass")

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
