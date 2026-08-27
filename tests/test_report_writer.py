from src.analyzer import analyze_sgf_file
from src.classifier import ClassifiedMistake, classify_selected_mistakes
from src.katago_client import CandidateMove, MockEngineClient, PositionAnalysis, PositionInput
from src.main import build_structured_review_for_game, print_sample_report
from src.mistake_selector import select_top_mistakes
from src.report_writer import generate_review_report
from src.sgf_parser import parse_sgf, parse_sgf_file


def test_generate_review_report_from_pipeline_data() -> None:
    game = parse_sgf_file("samples/sample_game.sgf")
    results = analyze_sgf_file("samples/sample_game.sgf", MockEngineClient(candidate_count=3))
    selected = select_top_mistakes(results, loss_threshold=1.0, limit=3)
    classified = classify_selected_mistakes(selected, results)

    report = generate_review_report(game, classified)

    assert "对局概况" in report
    assert "- 棋盘：19x19" in report
    assert "- 对局者：Black Player（黑） vs White Player（白）" in report
    assert "- 分析手数：4" in report
    assert "重点手" in report
    assert "1. 黑第3手：实战R4，推荐C6，损失1.80目，暂难归类" in report
    assert "2. 黑第1手：实战Q16，推荐R16，损失1.40目，局部用力过猛" in report
    assert "3. 白第2手：实战D16，推荐D3，损失1.20目，暂难归类" in report
    assert "逐手说明" in report
    assert "更好的选择是C6" in report
    assert "qp（R4）" not in report
    assert "这手的问题：" in report
    assert "训练建议" in report


def test_generate_review_report_unclear_classification_is_explicit() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]RU[Japanese]KM[6.5]PB[A]PW[B];B[pd])")
    mistakes = [
        ClassifiedMistake(
            move_number=1,
            played_move="pd",
            recommended_move="qd",
            estimated_loss=0.8,
            category="unclear",
        )
    ]

    report = generate_review_report(game, mistakes)

    assert "黑第1手（暂难归类）" in report
    assert "这手的信号不算单一，但从结果看还是明显亏了。" in report


def test_print_sample_report_for_sample_pipeline(capsys) -> None:
    print_sample_report("samples/sample_game.sgf", engine=MockEngineClient(candidate_count=3))
    out = capsys.readouterr().out

    assert "对局概况" in out
    assert "整局总结" in out
    assert "逐手说明" in out
    assert "训练建议" in out
    assert "黑第3手：实战R4，推荐C6，损失1.80目，暂难归类" in out


def test_generate_review_report_formats_pass_move() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]RU[Japanese]KM[6.5]PB[A]PW[B];B[])")
    mistakes = [
        ClassifiedMistake(
            move_number=1,
            played_move=None,
            recommended_move="qd",
            estimated_loss=1.1,
            category="defensive_overreaction",
        )
    ]

    report = generate_review_report(game, mistakes)

    assert "实战停一手" in report
    assert "推荐R16" in report


def test_generate_review_report_mentions_leave_main_battlefield() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]RU[Japanese]KM[6.5]PB[A]PW[B];B[qd];W[dp];B[cc])")
    review = build_structured_review_for_game(
        game,
        engine=_LeaveMainBattlefieldEngine(),
        loss_threshold=1.0,
        limit=3,
    )

    report = generate_review_report(
        game,
        [
            ClassifiedMistake(
                move_number=3,
                played_move="cc",
                recommended_move="pq",
                estimated_loss=1.8,
                category="tactical_blunder",
                winrate_delta=-0.09,
                severity="mistake",
            )
        ],
        review=review,
    )

    assert "主战场" in report


def test_generate_review_report_includes_positive_highlight_labels() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]RU[Japanese]KM[6.5]PB[A]PW[B];B[pd])")
    review = build_structured_review_for_game(
        game,
        engine=_PositiveMoveEngine(),
        loss_threshold=1.0,
        limit=3,
    )

    report = generate_review_report(game, [], review=review)

    assert "亮点手" in report
    assert "关键好手" in report
    assert "黑第1手" in report
    assert "Q16" in report


class _LeaveMainBattlefieldEngine:
    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        move_count = len(position.moves)

        if move_count == 0:
            return PositionAnalysis(
                best_move="qd",
                played_move=position.played_move,
                estimated_loss=0.0,
                score_estimate=2.0,
                winrate=0.56,
                played_score_estimate=2.0,
                played_winrate=0.56,
                top_candidates=(
                    CandidateMove("qd", score_estimate=2.0, winrate=0.56),
                    CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                    CandidateMove("pq", score_estimate=1.3, winrate=0.53),
                ),
                pv_summary="B qd -> W dp -> B pq",
            )

        if move_count == 1:
            return PositionAnalysis(
                best_move="dp",
                played_move=position.played_move,
                estimated_loss=0.0,
                score_estimate=1.5,
                winrate=0.54,
                played_score_estimate=1.5,
                played_winrate=0.54,
                top_candidates=(
                    CandidateMove("dp", score_estimate=1.5, winrate=0.54),
                    CandidateMove("pq", score_estimate=1.3, winrate=0.53),
                    CandidateMove("cq", score_estimate=1.1, winrate=0.52),
                ),
                pv_summary="W dp -> B pq -> W cq",
            )

        if move_count == 2 and position.played_move is not None:
            return PositionAnalysis(
                best_move="pq",
                played_move=position.played_move,
                estimated_loss=1.8,
                score_estimate=1.8,
                winrate=0.57,
                played_score_estimate=0.0,
                played_winrate=0.48,
                top_candidates=(
                    CandidateMove("pq", score_estimate=1.8, winrate=0.57),
                    CandidateMove("oq", score_estimate=1.5, winrate=0.54),
                    CandidateMove("pp", score_estimate=1.3, winrate=0.53),
                ),
                pv_summary="B pq -> W oq -> B pp",
            )

        return PositionAnalysis(
            best_move="dd",
            played_move=position.played_move,
            estimated_loss=0.0,
            score_estimate=0.8,
            winrate=0.52,
            played_score_estimate=0.8,
            played_winrate=0.52,
            top_candidates=(
                CandidateMove("dd", score_estimate=0.8, winrate=0.52),
                CandidateMove("pq", score_estimate=0.6, winrate=0.51),
                CandidateMove("pp", score_estimate=0.5, winrate=0.5),
            ),
            pv_summary="W dd -> B pq -> W pp",
        )


class _PositiveMoveEngine:
    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        if len(position.moves) == 0 and position.played_move is not None:
            return PositionAnalysis(
                best_move="qd",
                played_move=position.played_move,
                estimated_loss=0.0,
                score_estimate=0.4,
                winrate=0.49,
                played_score_estimate=2.1,
                played_winrate=0.61,
                top_candidates=(
                    CandidateMove("qd", score_estimate=0.4, winrate=0.49),
                    CandidateMove("dp", score_estimate=0.2, winrate=0.48),
                    CandidateMove("cq", score_estimate=0.1, winrate=0.47),
                ),
                pv_summary="B qd -> W dp -> B cq",
            )

        return PositionAnalysis(
            best_move="dd",
            played_move=position.played_move,
            estimated_loss=0.0,
            score_estimate=1.2,
            winrate=0.55,
            played_score_estimate=1.2,
            played_winrate=0.55,
            top_candidates=(
                CandidateMove("dd", score_estimate=1.2, winrate=0.55),
                CandidateMove("pq", score_estimate=1.0, winrate=0.53),
                CandidateMove("cp", score_estimate=0.8, winrate=0.52),
            ),
            pv_summary="W dd -> B pq -> W cq",
        )
