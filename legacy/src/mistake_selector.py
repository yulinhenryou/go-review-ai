from __future__ import annotations

from dataclasses import dataclass
import math

from src.analyzer import MoveAnalysisResult
from src.engine_types import EngineProtocolError
from src.game import validate_review_options
from src.mistake_severity import (
    DEFAULT_LOSS_THRESHOLD, DEFAULT_SEVERE_THRESHOLD, MAX_REVIEW_MISTAKES,
    MistakeSeverity, severity_from_loss,
)


@dataclass(frozen=True)
class MoveAssessment:
    raw_score_loss: float | None
    score_loss: float | None
    winrate_delta_pp: float | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SelectedMistake:
    move_number: int
    color: str
    played_move: str | None
    recommended_move: str
    score_loss: float
    raw_score_loss: float
    winrate_delta_pp: float | None
    severity: MistakeSeverity


def assess_move(result: MoveAnalysisResult) -> MoveAssessment:
    value = result.engine_analysis
    evidence = value.evidence
    warnings = list(evidence.warnings) if evidence else ["unverified_engine"]
    if evidence and (
        evidence.rules != result.position_input.rules
        or evidence.komi != result.position_input.komi
        or evidence.turn_number != len(result.position_input.moves)
        or evidence.value_perspective != "side_to_move"
        or evidence.score_unit != "points"
    ):
        raise EngineProtocolError("Move evidence does not match its input context")
    for number in (value.score_estimate, value.played_score_estimate, value.winrate, value.played_winrate):
        if number is not None and (isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number)):
            raise EngineProtocolError("Nonfinite move evidence")
    for rate in (value.winrate, value.played_winrate):
        if rate is not None and not 0 <= rate <= 1:
            raise EngineProtocolError("Winrate is outside the probability range")

    # The adapter owns comparable searches. A real played candidate is mandatory;
    # do not infer its value from another candidate or a neighbouring position.
    comparable = value.best_move is not None
    if evidence:
        played = value.played_candidate
        comparable = comparable and played is not None and played.move == (result.played_move or "pass")
    raw = None
    if comparable and value.score_estimate is not None and value.played_score_estimate is not None:
        raw = value.score_estimate - value.played_score_estimate
        if not math.isfinite(raw):
            raise EngineProtocolError("Nonfinite score difference")
    if raw is None:
        warnings.append("missing_score_evidence")
    elif raw < 0:
        warnings.append("negative_difference_search_noise")
    delta = None
    if comparable and value.winrate is not None and value.played_winrate is not None:
        delta = (value.played_winrate - value.winrate) * 100
    if delta is None:
        warnings.append("missing_winrate_evidence")
    return MoveAssessment(raw, max(0.0, raw) if raw is not None else None, delta, tuple(sorted(set(warnings))))


def select_mistakes_above_threshold(
    results: list[MoveAnalysisResult],
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> list[SelectedMistake]:
    validate_review_options(loss_threshold, MAX_REVIEW_MISTAKES, severe_threshold)
    selected = []
    for result in results:
        assessment = assess_move(result)
        severity = severity_from_loss(assessment.score_loss, loss_threshold, severe_threshold)
        if severity is not None:
            selected.append(SelectedMistake(
                result.move_number, result.color, result.played_move, result.recommended_move,
                assessment.score_loss, assessment.raw_score_loss, assessment.winrate_delta_pp, severity,
            ))
    return sorted(selected, key=lambda item: (-item.score_loss, item.move_number))


def select_top_mistakes(
    results: list[MoveAnalysisResult],
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD,
    limit: int = MAX_REVIEW_MISTAKES,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> list[SelectedMistake]:
    validate_review_options(loss_threshold, limit, severe_threshold)
    return select_mistakes_above_threshold(results, loss_threshold, severe_threshold)[:limit]


def print_mistake_summary(mistakes: list[SelectedMistake]) -> None:
    for mistake in mistakes:
        delta = f"{mistake.winrate_delta_pp:+.2f} pp" if mistake.winrate_delta_pp is not None else "unavailable"
        print(f"Move {mistake.move_number} ({mistake.color}): played={mistake.played_move or 'pass'} "
              f"recommended={mistake.recommended_move} loss={mistake.score_loss:.2f} "
              f"winrate_delta={delta} severity={mistake.severity}")
