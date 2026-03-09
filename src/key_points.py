from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from src.analyzer import MoveAnalysisResult
from src.chinese_explanations import (
    leave_main_battlefield_summary_cn,
    phase_label_cn,
    phase_overview_text,
    phase_summary_cn,
    plan_break_summary_cn,
    review_summary_total_cn,
    turning_point_summary_cn,
)
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
class LeaveMainBattlefield:
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
class ReviewSummary:
    opening: str
    middle_game: str
    endgame: str
    main_turning_points: list[str]
    loss_cause: MainIssue
    summary: str


@dataclass(frozen=True)
class KeyPointAnalysis:
    turning_points: list[TurningPoint]
    plan_breaks: list[PlanBreak]
    leave_main_battlefields: list[LeaveMainBattlefield]
    phase_summary: PhaseSummary
    review_summary: ReviewSummary


def build_key_point_analysis(
    results: list[MoveAnalysisResult],
    classified_results: list[ClassifiedMistake],
) -> KeyPointAnalysis:
    if len(results) != len(classified_results):
        raise ValueError("results and classified_results must have matching lengths")

    turning_points = _turning_points(results, classified_results)
    plan_breaks, leave_main_battlefields = _plan_breaks(results)
    phase_summary = _phase_summary(results, classified_results)
    review_summary = _review_summary(turning_points, phase_summary)
    return KeyPointAnalysis(
        turning_points=turning_points,
        plan_breaks=plan_breaks,
        leave_main_battlefields=leave_main_battlefields,
        phase_summary=phase_summary,
        review_summary=review_summary,
    )


def _turning_points(
    results: list[MoveAnalysisResult],
    classified_results: list[ClassifiedMistake],
) -> list[TurningPoint]:
    if not results:
        return []

    target_count = _turning_point_limit(len(results))
    if target_count == 0:
        return []

    eligible_indexes = [
        index
        for index in range(len(results))
        if _is_turning_point_candidate(results[index], classified_results[index], len(results))
    ]
    if not eligible_indexes:
        return []

    cliff_ranked_indexes = sorted(
        eligible_indexes,
        key=lambda index: _turning_point_cliff_rank(results[index], classified_results[index]),
        reverse=True,
    )
    ranked_indexes = sorted(
        eligible_indexes,
        key=lambda index: _turning_point_rank(results[index], classified_results[index]),
        reverse=True,
    )

    chosen_indexes: list[int] = []
    cluster_radius = 2 if len(results) < 80 else 4
    for index in cliff_ranked_indexes:
        if not _is_cliff_like_change(results[index], classified_results[index]):
            continue
        if index in chosen_indexes:
            continue
        chosen_indexes.append(index)
        if len(chosen_indexes) == target_count:
            break

    for index in ranked_indexes:
        if index in chosen_indexes:
            continue
        if any(
            abs(results[index].move_number - results[chosen].move_number) <= cluster_radius
            for chosen in chosen_indexes
        ):
            continue
        chosen_indexes.append(index)
        if len(chosen_indexes) == target_count:
            break

    chosen_indexes.sort(key=lambda index: results[index].move_number)

    return [
        _turning_point_view(results[index], classified_results[index], len(results))
        for index in chosen_indexes
    ]


def _turning_point_rank(
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
) -> tuple[float, float, float, int]:
    transition_bonus = 1.0 if _is_nearly_losing_transition(result) else 0.0
    return (
        abs(classified.winrate_delta),
        transition_bonus,
        result.estimated_loss + _severity_bonus(classified.severity),
        -result.move_number,
    )


def _turning_point_cliff_rank(
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
) -> tuple[float, float, float, int]:
    transition_bonus = 1.0 if _is_nearly_losing_transition(result) else 0.0
    return (
        abs(classified.winrate_delta) + transition_bonus,
        transition_bonus,
        result.estimated_loss,
        -result.move_number,
    )


def _turning_point_limit(total_moves: int) -> int:
    if total_moves < 20:
        return 0
    if total_moves < 50:
        return 1
    if total_moves < 120:
        return 2
    return min(5, 3 + int(total_moves >= 180) + int(total_moves >= 240))


def _is_turning_point_candidate(
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
    total_moves: int,
) -> bool:
    if _is_nearly_losing_transition(result):
        return True
    if total_moves < 50:
        return result.estimated_loss >= 2.5 or abs(classified.winrate_delta) >= 0.12
    if total_moves < 120:
        return result.estimated_loss >= 2.0 or abs(classified.winrate_delta) >= 0.1
    return result.estimated_loss >= 1.5 or abs(classified.winrate_delta) >= 0.08


def _is_cliff_like_change(
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
) -> bool:
    return abs(classified.winrate_delta) >= 0.14 or _is_nearly_losing_transition(result)


def _is_nearly_losing_transition(result: MoveAnalysisResult) -> bool:
    return (
        result.engine_analysis.winrate >= 0.45
        and result.engine_analysis.played_winrate <= 0.20
        and (result.engine_analysis.winrate - result.engine_analysis.played_winrate) >= 0.18
    )


def _severity_bonus(severity: MistakeSeverity) -> float:
    bonuses: dict[MistakeSeverity, float] = {
        "inaccuracy": 0.0,
        "mistake": 0.2,
        "major_mistake": 0.5,
        "blunder": 0.8,
    }
    return bonuses[severity]


def _turning_point_view(
    result: MoveAnalysisResult,
    classified: ClassifiedMistake,
    total_moves: int,
) -> TurningPoint:
    phase = phase_for_move(result.move_number, total_moves, result)
    return TurningPoint(
        move_number=result.move_number,
        color=result.color,
        score_loss=result.estimated_loss,
        winrate_delta=classified.winrate_delta,
        severity=classified.severity,
        phase=phase,
        summary=turning_point_summary_cn(
            color=result.color,
            move_number=result.move_number,
            phase=phase,
            score_loss=result.estimated_loss,
            winrate_delta=classified.winrate_delta,
        ),
    )


def _plan_breaks(
    results: list[MoveAnalysisResult],
) -> tuple[list[PlanBreak], list[LeaveMainBattlefield]]:
    plan_breaks: list[PlanBreak] = []
    leave_main_battlefields: list[LeaveMainBattlefield] = []

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

        if _is_leave_main_battlefield(anchor, reply, follow_up, pv_steps[2][1], winrate_delta):
            leave_main_battlefields.append(
                LeaveMainBattlefield(
                    anchor_move_number=anchor.move_number,
                    break_move_number=follow_up.move_number,
                    color=follow_up.color,
                    expected_follow_up=_normalize_move(pv_steps[2][1]),
                    played_move=follow_up.played_move,
                    score_loss=follow_up.estimated_loss,
                    summary=leave_main_battlefield_summary_cn(
                        anchor_move_number=anchor.move_number,
                        color=follow_up.color,
                        break_move_number=follow_up.move_number,
                        expected_follow_up=_display_move(
                            pv_steps[2][1], follow_up.position_input.board_size
                        ),
                        played_move=_display_move(
                            follow_up.played_move, follow_up.position_input.board_size
                        ),
                        score_loss=follow_up.estimated_loss,
                    ),
                )
            )
            continue

        plan_breaks.append(
            PlanBreak(
                anchor_move_number=anchor.move_number,
                break_move_number=follow_up.move_number,
                color=follow_up.color,
                expected_follow_up=_normalize_move(pv_steps[2][1]),
                played_move=follow_up.played_move,
                score_loss=follow_up.estimated_loss,
                summary=plan_break_summary_cn(
                    anchor_move_number=anchor.move_number,
                    color=follow_up.color,
                    break_move_number=follow_up.move_number,
                    expected_follow_up=_display_move(
                        pv_steps[2][1], follow_up.position_input.board_size
                    ),
                    played_move=_display_move(
                        follow_up.played_move, follow_up.position_input.board_size
                    ),
                    score_loss=follow_up.estimated_loss,
                ),
            )
        )

    return plan_breaks, leave_main_battlefields


def _is_leave_main_battlefield(
    anchor: MoveAnalysisResult,
    reply: MoveAnalysisResult,
    follow_up: MoveAnalysisResult,
    expected_follow_up: str | None,
    winrate_delta: float,
) -> bool:
    board_size = follow_up.position_input.board_size
    local_radius = max(2, board_size // 6)
    far_distance = max(5, board_size // 3)
    urgency_loss = max(1.5, round(board_size / 20, 2))
    urgency_winrate = 0.08

    if follow_up.played_move is None or expected_follow_up is None:
        return False
    if follow_up.estimated_loss < urgency_loss and abs(winrate_delta) < urgency_winrate:
        return False
    if not _engine_focuses_on_battlefield(follow_up, expected_follow_up, local_radius):
        return False

    battlefield_points = [
        _coord_to_point(anchor.played_move, board_size),
        _coord_to_point(reply.played_move, board_size),
        _coord_to_point(expected_follow_up, board_size),
    ]
    played_point = _coord_to_point(follow_up.played_move, board_size)
    if played_point is None:
        return False

    local_points = [point for point in battlefield_points if point is not None]
    if len(local_points) < 2:
        return False

    return all(
        _chebyshev_distance(played_point, point) >= far_distance
        for point in local_points
    )


def _engine_focuses_on_battlefield(
    follow_up: MoveAnalysisResult,
    expected_follow_up: str,
    local_radius: int,
) -> bool:
    board_size = follow_up.position_input.board_size
    expected_point = _coord_to_point(expected_follow_up, board_size)
    if expected_point is None:
        return False

    nearby_candidates = 0
    for candidate in follow_up.engine_analysis.top_candidates[:3]:
        candidate_point = _coord_to_point(candidate.move, board_size)
        if candidate_point is None:
            continue
        if _chebyshev_distance(candidate_point, expected_point) <= local_radius:
            nearby_candidates += 1

    return nearby_candidates >= 2


def _chebyshev_distance(
    left: tuple[int, int],
    right: tuple[int, int],
) -> int:
    return max(abs(left[0] - right[0]), abs(left[1] - right[1]))


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
        phase = phase_for_move(result.move_number, len(results), result)
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
        summary=phase_summary_cn(
            biggest_problem_phase=biggest_problem_phase,
            main_issue=main_issue,
        ),
    )


def _review_summary(
    turning_points: list[TurningPoint],
    phase_summary: PhaseSummary,
) -> ReviewSummary:
    return ReviewSummary(
        opening=phase_overview_text("opening", phase_summary.opening_loss),
        middle_game=phase_overview_text("middle_game", phase_summary.middle_game_loss),
        endgame=phase_overview_text("endgame", phase_summary.endgame_loss),
        main_turning_points=[
            f"第{item.move_number}手：{item.summary}"
            for item in turning_points
        ],
        loss_cause=phase_summary.main_issue,
        summary=review_summary_total_cn(
            main_issue=phase_summary.main_issue,
            biggest_problem_phase=phase_summary.biggest_problem_phase,
            turning_point_count=len(turning_points),
        ),
    )


def phase_for_move(
    move_number: int,
    total_moves: int,
    result: MoveAnalysisResult | None = None,
) -> GamePhase:
    if total_moves <= 1:
        return "opening"
    if result is None:
        return _fallback_phase(move_number, total_moves)

    features = _board_features(result)
    opening_score = 0
    middle_score = 0
    endgame_score = 0

    if move_number <= 20:
        opening_score += 3
    elif move_number <= 40:
        opening_score += 1
        middle_score += 1
    else:
        middle_score += 1

    if features.open_region_count >= 6:
        opening_score += 3
    elif features.open_region_count >= 4:
        opening_score += 2
    elif features.open_region_count >= 2:
        middle_score += 1
    else:
        endgame_score += 2

    if features.recent_contact_moves >= 3:
        middle_score += 3
    elif features.recent_contact_moves >= 1:
        middle_score += 1
    else:
        opening_score += 1

    if features.unstable_groups >= 3:
        middle_score += 3
    elif features.unstable_groups >= 1:
        middle_score += 2
    else:
        endgame_score += 1

    if features.occupied_ratio >= 0.45:
        endgame_score += 2
    elif features.occupied_ratio >= 0.25:
        middle_score += 1

    if (
        features.occupied_ratio >= 0.42
        and features.open_region_count <= 1
        and features.recent_contact_moves == 0
        and features.unstable_groups == 0
    ):
        endgame_score += 3

    if move_number < 40:
        endgame_score = -1

    scores: dict[GamePhase, int] = {
        "opening": opening_score,
        "middle_game": middle_score,
        "endgame": endgame_score,
    }
    return max(
        ("opening", "middle_game", "endgame"),
        key=lambda phase: (scores[phase], _phase_priority(phase)),
    )


def phase_label(phase: GamePhase) -> str:
    return phase_label_cn(phase)


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
    if phase == "endgame":
        return "endgame_loss"
    if category in {"direction_error", "defensive_overreaction"}:
        return "balance"
    if category in {"local_overplay", "tactical_blunder"}:
        return "fighting"
    return "balance" if phase == "opening" else "fighting"


def issue_label(issue: MainIssue) -> str:
    labels: dict[MainIssue, str] = {
        "balance": "形势判断",
        "fighting": "接触战",
        "endgame_loss": "官子",
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


def _display_move(move: str | None, board_size: int | None = None) -> str:
    normalized = _normalize_move(move)
    if normalized is None:
        return "pass"
    if board_size is None:
        return normalized
    human = _human_coord(normalized, board_size)
    return human if human is not None else normalized


def _human_coord(move: str, board_size: int) -> str | None:
    point = _coord_to_point(move, board_size)
    if point is None:
        return None
    x, y = point
    column_index = x + (1 if x >= 8 else 0)
    column = chr(ord("A") + column_index)
    row = board_size - y
    return f"{column}{row}"


@dataclass(frozen=True)
class _BoardFeatures:
    occupied_ratio: float
    open_region_count: int
    recent_contact_moves: int
    unstable_groups: int


def _fallback_phase(move_number: int, total_moves: int) -> GamePhase:
    if total_moves < 8:
        return "opening"
    if move_number < 40:
        if move_number <= max(12, total_moves // 3):
            return "opening"
        return "middle_game"
    if move_number <= max(20, total_moves // 4):
        return "opening"
    if move_number >= max(40, math.floor(total_moves * 0.8)):
        return "endgame"
    return "middle_game"


def _board_features(result: MoveAnalysisResult) -> _BoardFeatures:
    moves = list(result.position_input.moves)
    if result.played_move is not None:
        moves.append((result.color, result.played_move))

    board = _board_after_moves(result.position_input.board_size, moves)
    occupied_ratio = len(board) / (result.position_input.board_size ** 2)
    return _BoardFeatures(
        occupied_ratio=occupied_ratio,
        open_region_count=_open_region_count(result.position_input.board_size, board),
        recent_contact_moves=_recent_contact_moves(result.position_input.board_size, moves),
        unstable_groups=_unstable_group_count(result.position_input.board_size, board),
    )


def _board_after_moves(
    board_size: int,
    moves: list[tuple[str, str | None]],
) -> dict[tuple[int, int], str]:
    board: dict[tuple[int, int], str] = {}
    for color, move in moves:
        point = _coord_to_point(move, board_size)
        if point is None:
            continue
        board[point] = color
    return board


def _coord_to_point(move: str | None, board_size: int) -> tuple[int, int] | None:
    normalized = _normalize_move(move)
    if normalized is None or len(normalized) != 2:
        return None
    x = ord(normalized[0]) - ord("a")
    y = ord(normalized[1]) - ord("a")
    if not (0 <= x < board_size and 0 <= y < board_size):
        return None
    return (x, y)


def _neighbors(point: tuple[int, int], board_size: int) -> list[tuple[int, int]]:
    x, y = point
    candidates = ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
    return [
        (nx, ny)
        for nx, ny in candidates
        if 0 <= nx < board_size and 0 <= ny < board_size
    ]


def _open_region_count(
    board_size: int,
    board: dict[tuple[int, int], str],
) -> int:
    region_span = math.ceil(board_size / 3)
    open_regions = 0

    for start_x in range(0, board_size, region_span):
        for start_y in range(0, board_size, region_span):
            stones = 0
            for x in range(start_x, min(board_size, start_x + region_span)):
                for y in range(start_y, min(board_size, start_y + region_span)):
                    if (x, y) in board:
                        stones += 1
            if stones <= 2:
                open_regions += 1

    return open_regions


def _recent_contact_moves(
    board_size: int,
    moves: list[tuple[str, str | None]],
) -> int:
    history_board: dict[tuple[int, int], str] = {}
    contact_flags: list[bool] = []

    for color, move in moves:
        point = _coord_to_point(move, board_size)
        if point is None:
            contact_flags.append(False)
            continue
        is_contact = any(
            history_board.get(neighbor) not in {None, color}
            for neighbor in _neighbors(point, board_size)
        )
        contact_flags.append(is_contact)
        history_board[point] = color

    return sum(contact_flags[-8:])


def _unstable_group_count(
    board_size: int,
    board: dict[tuple[int, int], str],
) -> int:
    visited: set[tuple[int, int]] = set()
    unstable_groups = 0

    for point, color in board.items():
        if point in visited:
            continue
        group, liberties, enemy_contacts = _group_state(board_size, board, point, color)
        visited.update(group)
        if liberties <= 2 or (liberties == 3 and enemy_contacts >= 2):
            unstable_groups += 1

    return unstable_groups


def _group_state(
    board_size: int,
    board: dict[tuple[int, int], str],
    start: tuple[int, int],
    color: str,
) -> tuple[set[tuple[int, int]], int, int]:
    stack = [start]
    group: set[tuple[int, int]] = set()
    liberties: set[tuple[int, int]] = set()
    enemy_contacts = 0

    while stack:
        point = stack.pop()
        if point in group:
            continue
        group.add(point)
        for neighbor in _neighbors(point, board_size):
            neighbor_color = board.get(neighbor)
            if neighbor_color is None:
                liberties.add(neighbor)
            elif neighbor_color == color:
                if neighbor not in group:
                    stack.append(neighbor)
            else:
                enemy_contacts += 1

    return group, len(liberties), enemy_contacts
