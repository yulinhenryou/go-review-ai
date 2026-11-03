from pathlib import Path

from src.report_writer import generate_review_report
from src.review_service import build_review_outputs_for_game
from tests.report_fixtures import FixedEvidenceEngine, game_with_moves


def test_text_report_matches_structured_evidence_and_has_no_tactical_diagnosis():
    text, review = build_review_outputs_for_game(game_with_moves(2), FixedEvidenceEngine([4.2, 5.3]))
    assert text == generate_review_report(review)
    assert "第 2 手，白棋：实战 C17；推荐 Q16；估计损失 5.30 目" in text
    assert "白棋胜率相对推荐变化 -20.00 个百分点" in text
    assert "未完或结果未知" in text
    for forbidden in ("主战场", "思路中断", "用力过猛", "胜负主因", "布局阶段", "中盘阶段", "官子阶段", "训练建议"):
        assert forbidden not in text
    assert "模型 SHA-256" in text
    assert "配置 SHA-256" in text


def test_empty_complete_and_incomplete_reports_are_distinct():
    complete, _ = build_review_outputs_for_game(game_with_moves(1), FixedEvidenceEngine([0]))
    partial, _ = build_review_outputs_for_game(game_with_moves(1), FixedEvidenceEngine([None]))
    assert "未发现明显失误" in complete
    assert "报告不完整" in partial
    assert "未评估部分不能视为没有失误" in partial
    assert "不是完整的无失误结论" in partial


def test_retired_heuristics_are_not_in_production_modules():
    retired = {"classifier", "key_points", "chinese_explanations", "user_facing_labels"}
    for name in retired:
        assert not Path(f"src/{name}.py").exists()
    import ast
    for path in [*Path("src").glob("*.py"), *Path("app").glob("*.py")]:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {f"src.{name}" for name in retired}


def test_text_report_retains_input_variation_notice():
    from dataclasses import replace
    game = replace(game_with_moves(1), warnings=("first_variation_only",))
    text, _ = build_review_outputs_for_game(game, FixedEvidenceEngine([0]))
    assert "仅分析第一条主线" in text
