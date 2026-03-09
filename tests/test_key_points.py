from src.analyzer import MoveAnalysisResult
from src.classifier import ClassifiedMistake, classify_all_results
from src.katago_client import CandidateMove, PositionAnalysis, PositionInput
from src.key_points import build_key_point_analysis, parse_pv_summary, phase_for_move


def test_build_key_point_analysis_detects_turning_points_and_phase_summary() -> None:
    results = [
        _make_result(
            move_number=1,
            played_move="pd",
            best_move="qd",
            estimated_loss=1.6,
            top_candidates=(
                CandidateMove("qd", score_estimate=2.0, winrate=0.56),
                CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                CandidateMove("pq", score_estimate=1.0, winrate=0.52),
            ),
        ),
        _make_result(
            move_number=2,
            played_move="dd",
            best_move="dq",
            estimated_loss=0.6,
            top_candidates=(
                CandidateMove("dq", score_estimate=1.4, winrate=0.53),
                CandidateMove("cp", score_estimate=1.0, winrate=0.51),
                CandidateMove("qq", score_estimate=0.8, winrate=0.50),
            ),
        ),
        _make_result(
            move_number=3,
            played_move="qp",
            best_move="cn",
            estimated_loss=2.2,
            top_candidates=(
                CandidateMove("cn", score_estimate=2.3, winrate=0.58),
                CandidateMove("co", score_estimate=1.7, winrate=0.55),
                CandidateMove("bn", score_estimate=1.1, winrate=0.52),
            ),
        ),
        _make_result(
            move_number=4,
            played_move="dc",
            best_move="dq",
            estimated_loss=1.1,
            top_candidates=(
                CandidateMove("dq", score_estimate=0.9, winrate=0.52),
                CandidateMove("cp", score_estimate=0.5, winrate=0.50),
                CandidateMove("qq", score_estimate=0.2, winrate=0.49),
            ),
        ),
        _make_result(
            move_number=5,
            played_move="aa",
            best_move="ab",
            estimated_loss=2.7,
            top_candidates=(
                CandidateMove("ab", score_estimate=1.2, winrate=0.55),
                CandidateMove("bb", score_estimate=0.8, winrate=0.52),
                CandidateMove("ba", score_estimate=0.5, winrate=0.50),
            ),
        ),
        _make_result(
            move_number=6,
            played_move="bb",
            best_move="bc",
            estimated_loss=1.8,
            top_candidates=(
                CandidateMove("bc", score_estimate=0.9, winrate=0.52),
                CandidateMove("cc", score_estimate=0.6, winrate=0.50),
                CandidateMove("cb", score_estimate=0.4, winrate=0.49),
            ),
        ),
    ]
    classified = [
        ClassifiedMistake(1, "pd", "qd", 1.6, "direction_error", -0.07, "mistake"),
        ClassifiedMistake(2, "dd", "dq", 0.6, "unclear", -0.02, "inaccuracy"),
        ClassifiedMistake(3, "qp", "cn", 2.2, "local_overplay", -0.09, "mistake"),
        ClassifiedMistake(4, "dc", "dq", 1.1, "unclear", -0.05, "inaccuracy"),
        ClassifiedMistake(5, "aa", "ab", 2.7, "endgame_loss", -0.11, "mistake"),
        ClassifiedMistake(6, "bb", "bc", 1.8, "endgame_loss", -0.08, "mistake"),
    ]

    analysis = build_key_point_analysis(results, classified)

    assert analysis.turning_points == []
    assert analysis.phase_summary.biggest_problem_phase == "opening"
    assert analysis.phase_summary.main_issue == "balance"
    assert analysis.phase_summary.endgame_loss == 0.0
    assert analysis.phase_summary.summary == "全局看，损失主要集中在布局，主因是形势判断。"
    assert analysis.review_summary.loss_cause == "balance"
    assert analysis.review_summary.summary == (
        "这盘棋的胜负手主要出现在布局，核心问题是形势判断。全局最值得回看的关键点共有0处。"
    )


def test_build_key_point_analysis_detects_plan_break() -> None:
    results = [
        _make_result(
            move_number=1,
            played_move="qd",
            best_move="qd",
            estimated_loss=0.0,
            top_candidates=(
                CandidateMove("qd", score_estimate=2.0, winrate=0.56),
                CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                CandidateMove("pq", score_estimate=1.3, winrate=0.53),
            ),
            pv_summary="B qd -> W dp -> B pq",
        ),
        _make_result(
            move_number=2,
            played_move="dp",
            best_move="dp",
            estimated_loss=0.0,
            top_candidates=(
                CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                CandidateMove("pq", score_estimate=1.3, winrate=0.53),
                CandidateMove("cq", score_estimate=1.1, winrate=0.52),
            ),
            pv_summary="W dp -> B pq -> W cq",
        ),
        _make_result(
            move_number=3,
            played_move="oq",
            best_move="pq",
            estimated_loss=1.4,
            top_candidates=(
                CandidateMove("pq", score_estimate=1.6, winrate=0.55),
                CandidateMove("cq", score_estimate=1.3, winrate=0.53),
                CandidateMove("cp", score_estimate=1.1, winrate=0.52),
            ),
            pv_summary="B pq -> W cq -> B cp",
        ),
    ]
    classified = [
        ClassifiedMistake(1, "qd", "qd", 0.0, "unclear", 0.0, "inaccuracy"),
        ClassifiedMistake(2, "dp", "dp", 0.0, "unclear", 0.0, "inaccuracy"),
        ClassifiedMistake(3, "oq", "pq", 1.4, "tactical_blunder", -0.06, "inaccuracy"),
    ]

    analysis = build_key_point_analysis(results, classified)

    assert len(analysis.plan_breaks) == 1
    assert analysis.leave_main_battlefields == []
    assert analysis.plan_breaks[0].anchor_move_number == 1
    assert analysis.plan_breaks[0].break_move_number == 3
    assert analysis.plan_breaks[0].expected_follow_up == "pq"
    assert analysis.plan_breaks[0].played_move == "oq"
    assert "没有接上前面的思路" in analysis.plan_breaks[0].summary


def test_build_key_point_analysis_detects_leave_main_battlefield() -> None:
    results = [
        _make_result(
            move_number=1,
            played_move="qd",
            best_move="qd",
            estimated_loss=0.0,
            top_candidates=(
                CandidateMove("qd", score_estimate=2.0, winrate=0.56),
                CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                CandidateMove("pq", score_estimate=1.3, winrate=0.53),
            ),
            pv_summary="B qd -> W dp -> B pq",
        ),
        _make_result(
            move_number=2,
            played_move="dp",
            best_move="dp",
            estimated_loss=0.0,
            top_candidates=(
                CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                CandidateMove("pq", score_estimate=1.3, winrate=0.53),
                CandidateMove("cq", score_estimate=1.1, winrate=0.52),
            ),
            pv_summary="W dp -> B pq -> W cq",
        ),
        _make_result(
            move_number=3,
            played_move="cc",
            best_move="pq",
            estimated_loss=1.8,
            top_candidates=(
                CandidateMove("pq", score_estimate=1.8, winrate=0.57),
                CandidateMove("oq", score_estimate=1.5, winrate=0.54),
                CandidateMove("pp", score_estimate=1.3, winrate=0.53),
            ),
            pv_summary="B pq -> W oq -> B pp",
        ),
    ]
    classified = [
        ClassifiedMistake(1, "qd", "qd", 0.0, "unclear", 0.0, "inaccuracy"),
        ClassifiedMistake(2, "dp", "dp", 0.0, "unclear", 0.0, "inaccuracy"),
        ClassifiedMistake(3, "cc", "pq", 1.8, "tactical_blunder", -0.09, "mistake"),
    ]

    analysis = build_key_point_analysis(results, classified)

    assert analysis.plan_breaks == []
    assert len(analysis.leave_main_battlefields) == 1
    assert analysis.leave_main_battlefields[0].break_move_number == 3
    assert analysis.leave_main_battlefields[0].played_move == "cc"
    assert "脱离了主战场" in analysis.leave_main_battlefields[0].summary


def test_plan_break_and_leave_main_battlefield_summaries_use_distinct_teaching_tone() -> None:
    plan_break_summary = build_key_point_analysis(
        [
            _make_result(
                move_number=1,
                played_move="qd",
                best_move="qd",
                estimated_loss=0.0,
                top_candidates=(
                    CandidateMove("qd", score_estimate=2.0, winrate=0.56),
                    CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                    CandidateMove("pq", score_estimate=1.3, winrate=0.53),
                ),
                pv_summary="B qd -> W dp -> B pq",
            ),
            _make_result(
                move_number=2,
                played_move="dp",
                best_move="dp",
                estimated_loss=0.0,
                top_candidates=(
                    CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                    CandidateMove("pq", score_estimate=1.3, winrate=0.53),
                    CandidateMove("cq", score_estimate=1.1, winrate=0.52),
                ),
                pv_summary="W dp -> B pq -> W cq",
            ),
            _make_result(
                move_number=5,
                played_move="oq",
                best_move="pq",
                estimated_loss=1.4,
                top_candidates=(
                    CandidateMove("pq", score_estimate=1.6, winrate=0.55),
                    CandidateMove("cq", score_estimate=1.3, winrate=0.53),
                    CandidateMove("cp", score_estimate=1.1, winrate=0.52),
                ),
                pv_summary="B pq -> W cq -> B cp",
            ),
        ],
        [
            ClassifiedMistake(1, "qd", "qd", 0.0, "unclear", 0.0, "inaccuracy"),
            ClassifiedMistake(2, "dp", "dp", 0.0, "unclear", 0.0, "inaccuracy"),
            ClassifiedMistake(5, "oq", "pq", 1.4, "tactical_blunder", -0.06, "inaccuracy"),
        ],
    ).plan_breaks[0].summary

    leave_main_battlefield_summary = build_key_point_analysis(
        [
            _make_result(
                move_number=1,
                played_move="qd",
                best_move="qd",
                estimated_loss=0.0,
                top_candidates=(
                    CandidateMove("qd", score_estimate=2.0, winrate=0.56),
                    CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                    CandidateMove("pq", score_estimate=1.3, winrate=0.53),
                ),
                pv_summary="B qd -> W dp -> B pq",
            ),
            _make_result(
                move_number=2,
                played_move="dp",
                best_move="dp",
                estimated_loss=0.0,
                top_candidates=(
                    CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                    CandidateMove("pq", score_estimate=1.3, winrate=0.53),
                    CandidateMove("cq", score_estimate=1.1, winrate=0.52),
                ),
                pv_summary="W dp -> B pq -> W cq",
            ),
            _make_result(
                move_number=5,
                played_move="cc",
                best_move="pq",
                estimated_loss=1.8,
                top_candidates=(
                    CandidateMove("pq", score_estimate=1.8, winrate=0.57),
                    CandidateMove("oq", score_estimate=1.5, winrate=0.54),
                    CandidateMove("pp", score_estimate=1.3, winrate=0.53),
                ),
                pv_summary="B pq -> W oq -> B pp",
            ),
        ],
        [
            ClassifiedMistake(1, "qd", "qd", 0.0, "unclear", 0.0, "inaccuracy"),
            ClassifiedMistake(2, "dp", "dp", 0.0, "unclear", 0.0, "inaccuracy"),
            ClassifiedMistake(5, "cc", "pq", 1.8, "tactical_blunder", -0.09, "mistake"),
        ],
    ).leave_main_battlefields[0].summary

    assert "局部" in plan_break_summary or "处理" in plan_break_summary
    assert "主战场" not in plan_break_summary
    assert "主战场" in leave_main_battlefield_summary


def test_parse_pv_summary_and_phase_for_move_are_deterministic() -> None:
    assert parse_pv_summary("B qd -> W dp -> B pq") == [
        ("B", "qd"),
        ("W", "dp"),
        ("B", "pq"),
    ]
    assert phase_for_move(1, 4) == "opening"
    assert phase_for_move(2, 4) == "opening"
    assert phase_for_move(4, 4) == "opening"


def test_short_game_never_labels_endgame_or_multiple_turning_points() -> None:
    results = [
        _make_result(
            move_number=1,
            played_move="pd",
            best_move="qd",
            estimated_loss=1.4,
            top_candidates=(
                CandidateMove("qd", score_estimate=1.8, winrate=0.54),
                CandidateMove("dp", score_estimate=1.4, winrate=0.52),
                CandidateMove("pq", score_estimate=1.0, winrate=0.5),
            ),
        ),
        _make_result(
            move_number=2,
            played_move="dd",
            best_move="dq",
            estimated_loss=1.2,
            top_candidates=(
                CandidateMove("dq", score_estimate=1.6, winrate=0.53),
                CandidateMove("cp", score_estimate=1.3, winrate=0.51),
                CandidateMove("qq", score_estimate=1.0, winrate=0.5),
            ),
        ),
        _make_result(
            move_number=3,
            played_move="qp",
            best_move="cn",
            estimated_loss=1.8,
            top_candidates=(
                CandidateMove("cn", score_estimate=2.0, winrate=0.56),
                CandidateMove("co", score_estimate=1.6, winrate=0.53),
                CandidateMove("bn", score_estimate=1.2, winrate=0.5),
            ),
        ),
        _make_result(
            move_number=4,
            played_move="dc",
            best_move="dq",
            estimated_loss=1.1,
            top_candidates=(
                CandidateMove("dq", score_estimate=1.4, winrate=0.52),
                CandidateMove("cp", score_estimate=1.0, winrate=0.5),
                CandidateMove("qq", score_estimate=0.8, winrate=0.49),
            ),
        ),
    ]
    classified = [
        ClassifiedMistake(1, "pd", "qd", 1.4, "local_overplay", -0.06, "inaccuracy"),
        ClassifiedMistake(2, "dd", "dq", 1.2, "unclear", -0.05, "inaccuracy"),
        ClassifiedMistake(3, "qp", "cn", 1.8, "unclear", -0.08, "mistake"),
        ClassifiedMistake(4, "dc", "dq", 1.1, "unclear", -0.04, "inaccuracy"),
    ]

    analysis = build_key_point_analysis(results, classified)

    assert analysis.turning_points == []
    assert {
        phase_for_move(result.move_number, len(results), result)
        for result in results
    } == {"opening"}


def test_late_game_winrate_collapse_is_flagged_as_turning_point() -> None:
    results: list[MoveAnalysisResult] = []
    for move_number in range(1, 61):
        if move_number == 18:
            results.append(
                _make_result(
                    move_number=move_number,
                    played_move="qp",
                    best_move="cn",
                    estimated_loss=2.6,
                    top_candidates=(
                        CandidateMove("cn", score_estimate=2.4, winrate=0.58),
                        CandidateMove("co", score_estimate=1.8, winrate=0.55),
                        CandidateMove("bn", score_estimate=1.2, winrate=0.50),
                    ),
                )
            )
            continue

        if move_number == 58:
            results.append(
                _make_result(
                    move_number=move_number,
                    played_move="aa",
                    best_move="ab",
                    estimated_loss=1.2,
                    top_candidates=(
                        CandidateMove("ab", score_estimate=1.8, winrate=0.62),
                        CandidateMove("aa", score_estimate=-0.4, winrate=0.18),
                        CandidateMove("ba", score_estimate=-0.6, winrate=0.15),
                    ),
                )
            )
            continue

        results.append(
            _make_result(
                move_number=move_number,
                played_move="pd",
                best_move="qd",
                estimated_loss=0.2,
                top_candidates=(
                    CandidateMove("qd", score_estimate=0.6, winrate=0.51),
                    CandidateMove("pd", score_estimate=0.5, winrate=0.50),
                    CandidateMove("dp", score_estimate=0.4, winrate=0.49),
                ),
            )
        )

    classified = classify_all_results(results)

    analysis = build_key_point_analysis(results, classified)

    assert classified[57].severity == "blunder"
    assert [item.move_number for item in analysis.turning_points] == [18, 58]
    assert analysis.turning_points[-1].severity == "blunder"
    assert analysis.turning_points[-1].winrate_delta == -0.44


def _make_result(
    move_number: int,
    played_move: str | None,
    best_move: str,
    estimated_loss: float,
    top_candidates: tuple[CandidateMove, ...],
    pv_summary: str = "",
) -> MoveAnalysisResult:
    color = "B" if move_number % 2 == 1 else "W"
    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play=color,
        moves=tuple(),
        played_move=played_move,
    )
    played_candidate = _played_candidate(top_candidates, played_move)
    analysis = PositionAnalysis(
        best_move=best_move,
        played_move=played_move,
        estimated_loss=estimated_loss,
        score_estimate=top_candidates[0].score_estimate,
        winrate=top_candidates[0].winrate,
        played_score_estimate=played_candidate.score_estimate,
        played_winrate=played_candidate.winrate,
        top_candidates=top_candidates,
        pv_summary=pv_summary,
    )
    return MoveAnalysisResult(
        move_number=move_number,
        color=color,
        played_move=played_move,
        recommended_move=best_move,
        estimated_loss=estimated_loss,
        position_input=position,
        engine_analysis=analysis,
    )


def _played_candidate(
    top_candidates: tuple[CandidateMove, ...],
    played_move: str | None,
) -> CandidateMove:
    if not played_move:
        return top_candidates[0]

    for candidate in top_candidates:
        if candidate.move == played_move:
            return candidate

    fallback = top_candidates[-1]
    return CandidateMove(
        move=played_move,
        score_estimate=round(fallback.score_estimate - 0.3, 2),
        winrate=max(0.0, round(fallback.winrate - 0.02, 2)),
    )
