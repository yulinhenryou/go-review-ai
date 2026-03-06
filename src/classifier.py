from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from src.analyzer import MoveAnalysisResult
from src.mistake_selector import SelectedMistake

MistakeCategory = Literal[
    "direction_error",
    "local_overplay",
    "defensive_overreaction",
    "endgame_loss",
    "tactical_blunder",
    "unclear",
]

_CATEGORY_ORDER: tuple[MistakeCategory, ...] = (
    "direction_error",
    "local_overplay",
    "defensive_overreaction",
    "endgame_loss",
    "tactical_blunder",
    "unclear",
)


@dataclass(frozen=True)
class MistakeFeatures:
    move_number: int
    estimated_loss: float
    played_is_candidate: bool
    played_rank: int | None
    distance_to_best: int | None
    top_score_gap: float


@dataclass(frozen=True)
class ClassifiedMistake:
    move_number: int
    played_move: str | None
    recommended_move: str
    estimated_loss: float
    category: MistakeCategory


def classify_selected_mistakes(
    selected: list[SelectedMistake], results: list[MoveAnalysisResult]
) -> list[ClassifiedMistake]:
    by_move = {result.move_number: result for result in results}
    classified: list[ClassifiedMistake] = []

    for mistake in selected:
        result = by_move.get(mistake.move_number)
        if result is None:
            raise ValueError(f"No analysis result for move {mistake.move_number}")

        category = classify_mistake(extract_features(result))
        classified.append(
            ClassifiedMistake(
                move_number=mistake.move_number,
                played_move=mistake.played_move,
                recommended_move=mistake.recommended_move,
                estimated_loss=mistake.estimated_loss,
                category=category,
            )
        )

    return classified


def extract_features(result: MoveAnalysisResult) -> MistakeFeatures:
    top_candidates = result.engine_analysis.top_candidates
    played_move = result.played_move
    played_rank: int | None = None

    for index, candidate in enumerate(top_candidates, start=1):
        if candidate.move == played_move:
            played_rank = index
            break

    top_score_gap = (
        round(top_candidates[0].score_estimate - top_candidates[1].score_estimate, 2)
        if len(top_candidates) >= 2
        else 99.0
    )

    return MistakeFeatures(
        move_number=result.move_number,
        estimated_loss=result.estimated_loss,
        played_is_candidate=played_rank is not None,
        played_rank=played_rank,
        distance_to_best=_distance(result.played_move, result.recommended_move),
        top_score_gap=top_score_gap,
    )


def classify_mistake(features: MistakeFeatures) -> MistakeCategory:
    # Late-game value loss.
    if features.move_number >= 120 and features.estimated_loss >= 0.8:
        return "endgame_loss"

    # Large miss that likely drops a tactical point.
    if (
        features.estimated_loss >= 2.5
        and (not features.played_is_candidate or (features.played_rank or 0) >= 3)
    ):
        return "tactical_blunder"

    # Nearby but absent from top candidates usually implies forcing too hard.
    if (
        features.distance_to_best is not None
        and features.distance_to_best <= 2
        and not features.played_is_candidate
        and 1.0 <= features.estimated_loss < 2.5
    ):
        return "local_overplay"

    # Choosing a nearby second-choice move with modest top gap can be over-defensive.
    if (
        features.distance_to_best is not None
        and features.distance_to_best <= 2
        and features.played_rank == 2
        and features.top_score_gap <= 0.5
        and 0.7 <= features.estimated_loss <= 1.8
    ):
        return "defensive_overreaction"

    # Opening direction mistakes tend to be early with a far-away preferred direction.
    if (
        features.move_number <= 40
        and features.distance_to_best is not None
        and features.distance_to_best >= 6
        and features.played_is_candidate
        and (features.played_rank or 0) >= 2
        and features.top_score_gap <= 0.8
        and features.estimated_loss >= 0.8
    ):
        return "direction_error"

    return "unclear"


def print_classification_summary(classified: list[ClassifiedMistake]) -> None:
    if not classified:
        print("No selected mistakes to classify.")
        return

    for item in classified:
        played = item.played_move if item.played_move is not None else "pass"
        print(
            f"Move {item.move_number}: "
            f"played={played} recommended={item.recommended_move} "
            f"loss={item.estimated_loss:.2f} category={item.category}"
        )

    counts = Counter(item.category for item in classified)
    summary = ", ".join(
        f"{category}={counts[category]}" for category in _CATEGORY_ORDER if counts[category]
    )
    print(f"Category totals: {summary}")


def _distance(move_a: str | None, move_b: str | None) -> int | None:
    point_a = _parse_point(move_a)
    point_b = _parse_point(move_b)
    if point_a is None or point_b is None:
        return None
    return abs(point_a[0] - point_b[0]) + abs(point_a[1] - point_b[1])


def _parse_point(move: str | None) -> tuple[int, int] | None:
    if move is None or len(move) != 2:
        return None
    file_code = ord(move[0]) - ord("a")
    rank_code = ord(move[1]) - ord("a")
    if file_code < 0 or rank_code < 0:
        return None
    return (file_code, rank_code)
