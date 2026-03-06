from __future__ import annotations

from dataclasses import dataclass

from src.analyzer import MoveAnalysisResult


@dataclass(frozen=True)
class SelectedMistake:
    move_number: int
    played_move: str | None
    recommended_move: str
    estimated_loss: float


def select_top_mistakes(
    results: list[MoveAnalysisResult],
    loss_threshold: float,
    limit: int = 3,
) -> list[SelectedMistake]:
    """Select highest-impact mistakes above threshold, ordered by loss desc."""
    if loss_threshold < 0:
        raise ValueError("loss_threshold must be >= 0")
    if limit < 0:
        raise ValueError("limit must be >= 0")

    filtered = [r for r in results if r.estimated_loss >= loss_threshold]
    filtered.sort(key=lambda r: (-r.estimated_loss, r.move_number))

    return [
        SelectedMistake(
            move_number=r.move_number,
            played_move=r.played_move,
            recommended_move=r.recommended_move,
            estimated_loss=r.estimated_loss,
        )
        for r in filtered[:limit]
    ]


def print_mistake_summary(mistakes: list[SelectedMistake]) -> None:
    for mistake in mistakes:
        played = mistake.played_move if mistake.played_move is not None else "pass"
        print(
            f"Move {mistake.move_number}: "
            f"played={played} recommended={mistake.recommended_move} "
            f"loss={mistake.estimated_loss:.2f}"
        )
