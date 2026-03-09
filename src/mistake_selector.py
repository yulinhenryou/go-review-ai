from __future__ import annotations

from dataclasses import dataclass

from src.analyzer import MoveAnalysisResult
from src.mistake_severity import DEFAULT_SEVERITY_THRESHOLDS, MistakeSeverity, severity_from_loss


@dataclass(frozen=True)
class SelectedMistake:
    move_number: int
    played_move: str | None
    recommended_move: str
    estimated_loss: float
    winrate_delta: float = 0.0
    severity: MistakeSeverity = "inaccuracy"

    @property
    def score_loss(self) -> float:
        return self.estimated_loss


def select_mistakes_above_threshold(
    results: list[MoveAnalysisResult],
    loss_threshold: float,
) -> list[SelectedMistake]:
    """Select all mistakes at or above threshold, ordered by score loss desc."""
    if loss_threshold < 0:
        raise ValueError("loss_threshold must be >= 0")

    filtered = [r for r in results if r.estimated_loss >= loss_threshold]
    filtered.sort(key=lambda r: (-r.estimated_loss, r.move_number))

    return [_selected_mistake_from_result(result) for result in filtered]


def select_top_mistakes(
    results: list[MoveAnalysisResult],
    loss_threshold: float,
    limit: int = 3,
) -> list[SelectedMistake]:
    """Select the top-N presentation slice from threshold-qualified mistakes."""
    if limit < 0:
        raise ValueError("limit must be >= 0")

    return select_mistakes_above_threshold(results, loss_threshold=loss_threshold)[:limit]


def print_mistake_summary(mistakes: list[SelectedMistake]) -> None:
    for mistake in mistakes:
        played = mistake.played_move if mistake.played_move is not None else "pass"
        print(
            f"Move {mistake.move_number}: "
            f"played={played} recommended={mistake.recommended_move} "
            f"loss={mistake.score_loss:.2f} winrate_delta={mistake.winrate_delta:.2f} "
            f"severity={mistake.severity}"
        )


def _selected_mistake_from_result(result: MoveAnalysisResult) -> SelectedMistake:
    winrate_delta = round(
        result.engine_analysis.played_winrate - result.engine_analysis.winrate,
        2,
    )
    return SelectedMistake(
        move_number=result.move_number,
        played_move=result.played_move,
        recommended_move=result.recommended_move,
        estimated_loss=result.estimated_loss,
        winrate_delta=winrate_delta,
        severity=severity_from_loss(
            result.estimated_loss,
            thresholds=DEFAULT_SEVERITY_THRESHOLDS,
            winrate_delta=result.engine_analysis.played_winrate - result.engine_analysis.winrate,
            winrate_before=result.engine_analysis.winrate,
            winrate_after=result.engine_analysis.played_winrate,
        ),
    )
