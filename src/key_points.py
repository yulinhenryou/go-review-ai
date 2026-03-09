from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.analyzer import MoveAnalysisResult
from src.classifier import ClassifiedMistake, MistakeCategory
from src.mistake_severity import MistakeSeverity

GamePhase = Literal["opening", "middle_game", "endgame"]
MainIssue = Literal["balance", "fighting", "endgame_loss"]


@dataclass(frozen=True)
class TurningPoint:
    move_number: int
    color: str
    score_loss: float
    winrate_delta: float
    severity: MistakeSeverity
    phase: GamePhase
    summary: str


@dataclass(frozen=True)
class PlanBreak:
    anchor_move_number: int
    break_move_number: int
    color: str
    expected_follow_up: str | None
    played_move: str | None
    score_loss: float
    summary: str


@dataclass(frozen=True)
class PhaseSummary:
    opening_loss: float
    middle_game_loss: float
    endgame_loss: float
    biggest_problem_phase: GamePhase
    main_issue: MainIssue
    summary: str


@dataclass(frozen=True)
class KeyPointAnalysis:
    turning_points: list[TurningPoint]
    plan_breaks: list[PlanBreak]
    phase_summary: PhaseSummary


def build_key_point_analysis(
    results: list[MoveAnalysisResult],
    classified_results: list[ClassifiedMistake],
) -> KeyPointAnalysis:
    if len(results) != len(classified_results):
        raise ValueError("results and classified_results must have matching lengths")

    turning_points = _turning_points(results, classified_results)
    plan_breaks = _plan_breaks(results)
    phase_summary = _phase_summary(results, classified_results)
    return KeyPointAnalysis(
        turning_points=turning_points,
        plan_breaks=plan_breaks,
        phase_summary=phase_summary,
    )


def _turning_points(
    results: list[MoveAnalysisResult],
    classified_results: list[ClassifiedMistake],
) -> list[TurningPoint]:
    if not results:
        return []

    target_count = min(len(results), 3 + int(len(results) >= 90) + int(len(results) >= 180))
    ranked_indexes = sorted(
        range(len(results)),
        key=lambda index: _turning_point_rank(results[index], classified_results[index]),
        reverse=True,
    )

    shortlisted = [
        index
        for index in ranked_indexes
        if _is_major_swing(results[index], classified_results[index])
    ]
    chosen_indexes = shortlisted[:target_count]

    if len(chosen_indexes) < target_count:
        for index in ranked_indexes:
            if index in chosen_indexes:
                continue
            chosen_indexes.append(index)
            if len(chosen_indexes) == target_count:
                break

    return [
        _turning_point_view(results[index], classified_results[index], len(results))
        for index in chosen_indexes
    ]


def _turning_point_rank(
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
) -> tuple[float, float, int]:
    return (
        result.estimated_loss,
        abs(classified.winrate_delta),
        -result.move_number,
    )


def _is_major_swing(
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
) -> bool:
    return result.estimated_loss >= 1.5 or abs(classified.winrate_delta) >= 0.07


def _turning_point_view(
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
    total_moves: int,
) -> TurningPoint:
    phase = phase_for_move(result.move_number, total_moves)
    return TurningPoint(
        move_number=result.move_number,
        color=result.color,
        score_loss=result.estimated_loss,
        winrate_delta=classified.winrate_delta,
        severity=classified.severity,
        phase=phase,
        summary=(
            f"Move {result.move_number} created a major swing in the {phase_label(phase)} "
            f"with loss {result.estimated_loss:.2f} and winrate change {classified.winrate_delta:.0%}."
        ),
    )


def _plan_breaks(results: list[MoveAnalysisResult]) -> list[PlanBreak]:
    detected: list[PlanBreak] = []

    for index in range(len(results) - 2):
        anchor = results[index]
        reply = results[index + 1]
        follow_up = results[index + 2]
        pv_steps = parse_pv_summary(anchor.engine_analysis.pv_summary)

        if len(pv_steps) < 3:
            continue
        if anchor.played_move != anchor.recommended_move:
            continue
        if pv_steps[0] != (anchor.color, anchor.recommended_move):
            continue
        if reply.color != pv_steps[1][0] or reply.played_move != pv_steps[1][1]:
            continue
        if follow_up.color != pv_steps[2][0]:
            continue
        if follow_up.played_move == pv_steps[2][1]:
            continue

        winrate_delta = round(
            follow_up.engine_analysis.played_winrate - follow_up.engine_analysis.winrate,
            2,
        )
        if follow_up.estimated_loss < 1.0 and abs(winrate_delta) < 0.05:
            continue

        detected.append(
            PlanBreak(
                anchor_move_number=anchor.move_number,
                break_move_number=follow_up.move_number,
                color=follow_up.color,
                expected_follow_up=_normalize_move(pv_steps[2][1]),
                played_move=follow_up.played_move,
                score_loss=follow_up.estimated_loss,
                summary=(
                    f"After move {anchor.move_number}, the expected follow-up was "
                    f"{_display_move(pv_steps[2][1])}, but move {follow_up.move_number} "
                    f"played {_display_move(follow_up.played_move)} and lost {follow_up.estimated_loss:.2f}."
                ),
            )
        )

    return detected


def _phase_summary(
    results: list[MoveAnalysisResult],
    classified_results: list[ClassifiedMistake],
) -> PhaseSummary:
    losses: dict[GamePhase, float] = {
        "opening": 0.0,
        "middle_game": 0.0,
        "endgame": 0.0,
    }
    issue_weights: dict[MainIssue, float] = {
        "balance": 0.0,
        "fighting": 0.0,
        "endgame_loss": 0.0,
    }

    for result, classified in zip(results, classified_results, strict=True):
        phase = phase_for_move(result.move_number, len(results))
        losses[phase] += result.estimated_loss
        issue_weights[_issue_for_result(phase, classified.category)] += result.estimated_loss

    biggest_problem_phase = max(
        ("opening", "middle_game", "endgame"),
        key=lambda phase: (losses[phase], _phase_priority(phase)),
    )
    main_issue = max(
        ("balance", "fighting", "endgame_loss"),
        key=lambda issue: (issue_weights[issue], _issue_priority(issue)),
    )

    return PhaseSummary(
        opening_loss=round(losses["opening"], 2),
        middle_game_loss=round(losses["middle_game"], 2),
        endgame_loss=round(losses["endgame"], 2),
        biggest_problem_phase=biggest_problem_phase,
        main_issue=main_issue,
        summary=(
            f"The biggest problems came in the {phase_label(biggest_problem_phase)}, "
            f"with the main issue being {issue_label(main_issue)}."
        ),
    )


def phase_for_move(move_number: int, total_moves: int) -> GamePhase:
    if total_moves <= 1:
        return "opening"
    if total_moves == 2:
        return "opening" if move_number == 1 else "endgame"

    opening_end = max(1, total_moves // 3)
    endgame_start = max(opening_end + 1, total_moves - max(1, total_moves // 3) + 1)

    if move_number <= opening_end:
        return "opening"
    if move_number >= endgame_start:
        return "endgame"
    return "middle_game"


def phase_label(phase: GamePhase) -> str:
    labels: dict[GamePhase, str] = {
        "opening": "opening",
        "middle_game": "middle game",
        "endgame": "endgame",
    }
    return labels[phase]


def parse_pv_summary(pv_summary: str) -> list[tuple[str, str | None]]:
    steps: list[tuple[str, str | None]] = []

    for raw_step in pv_summary.split("->"):
        tokens = raw_step.strip().split()
        if len(tokens) != 2:
            return []
        color, move = tokens
        if color not in {"B", "W"}:
            return []
        steps.append((color, _normalize_move(move)))

    return steps


def _issue_for_result(phase: GamePhase, category: MistakeCategory) -> MainIssue:
    if category == "endgame_loss" or phase == "endgame":
        return "endgame_loss"
    if category in {"direction_error", "defensive_overreaction"}:
        return "balance"
    if category in {"local_overplay", "tactical_blunder"}:
        return "fighting"
    return "balance" if phase == "opening" else "fighting"


def issue_label(issue: MainIssue) -> str:
    labels: dict[MainIssue, str] = {
        "balance": "balance",
        "fighting": "fighting",
        "endgame_loss": "endgame loss",
    }
    return labels[issue]


def _phase_priority(phase: GamePhase) -> int:
    order: dict[GamePhase, int] = {
        "opening": 0,
        "middle_game": 1,
        "endgame": 2,
    }
    return order[phase]


def _issue_priority(issue: MainIssue) -> int:
    order: dict[MainIssue, int] = {
        "balance": 0,
        "fighting": 1,
        "endgame_loss": 2,
    }
    return order[issue]


def _normalize_move(move: str | None) -> str | None:
    if move is None:
        return None
    lowered = move.lower()
    if lowered == "pass":
        return None
    return lowered


def _display_move(move: str | None) -> str:
    normalized = _normalize_move(move)
    return normalized if normalized is not None else "pass"
