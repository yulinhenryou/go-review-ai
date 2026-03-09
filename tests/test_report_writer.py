from src.analyzer import analyze_sgf_file
from src.classifier import ClassifiedMistake, classify_selected_mistakes
from src.katago_client import MockEngineClient
from src.main import print_sample_report
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
    assert "1. 第3手：实战qp（R4），推荐cn（C6），损失1.80目，暂难归类" in report
    assert "2. 第1手：实战pd（Q16），推荐qd（R16），损失1.40目，局部用力过猛" in report
    assert "3. 第2手：实战dd（D16），推荐dq（D3），损失1.20目，暂难归类" in report
    assert "逐手说明" in report
    assert "更好的选择是cn（C6）" in report
    assert "这手的问题：" in report
    assert "训练建议" in report


def test_generate_review_report_unclear_classification_is_explicit() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]KM[6.5]PB[A]PW[B];B[pd])")
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

    assert "第1手（暂难归类）" in report
    assert "这手的信号不算单一，但从结果看还是明显亏了。" in report


def test_print_sample_report_for_sample_pipeline(capsys) -> None:
    print_sample_report("samples/sample_game.sgf", engine=MockEngineClient(candidate_count=3))
    out = capsys.readouterr().out

    assert "对局概况" in out
    assert "整局总结" in out
    assert "逐手说明" in out
    assert "训练建议" in out
    assert "第3手：实战qp（R4），推荐cn（C6），损失1.80目，暂难归类" in out


def test_generate_review_report_formats_pass_move() -> None:
    game = parse_sgf("(;FF[4]GM[1]SZ[19]KM[6.5]PB[A]PW[B];B[])")
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
    assert "推荐qd（R16）" in report
