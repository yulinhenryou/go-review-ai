from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from src.review_result import CoverageResult, ReviewResult


QUALITY_NOTES = {
    "unverified_engine": "此结果来自测试替身，不是真实引擎验收结果。",
    "negative_difference_search_noise": "存在负的原始目差，可能受搜索噪声影响；目损按 0 处理，不判为好手。",
    "low_visits": "部分候选搜索次数较少，估计值可能不稳定。",
    "separate_search": "部分实战落子来自独立补充搜索；相同预算不代表相同精度。",
    "played_evaluation_unavailable": "部分实战落子缺少引擎评估。",
    "missing_score_evidence": "部分手缺少可比较的目数证据，未参与失误判定。",
    "missing_winrate_evidence": "部分手的胜率变化不可用。",
    "missing_current_value": "记录末尾局面的评估不完整。",
    "missing_pv": "部分推荐缺少变化图，未补造后续着手。",
    "recommendation_unavailable": "部分局面没有可用推荐。",
    "no_candidate_moves": "记录末尾局面没有候选着手。",
    "missing_value": "部分推荐数值缺失。",
    "missing_played_value": "部分实战落子数值缺失。",
}


def quality_notes(warnings: Iterable[str]) -> tuple[str, ...]:
    # Unknown engine warnings stay available as codes, without echoing raw logs.
    return tuple(dict.fromkeys(QUALITY_NOTES.get(code, "引擎报告了额外质量警告。") for code in sorted(set(warnings))))


def move_summary(number: int, color: str, played: str, recommended: str | None,
                 loss: float | None, delta_pp: float | None) -> str:
    player = "黑" if color == "B" else "白"
    text = f"第 {number} 手，{player}棋：实战 {played}；推荐 {recommended or '不可用'}；"
    text += f"估计损失 {loss:.2f} 目。" if loss is not None else "目数证据不足，未判定失误。"
    text += f"{player}棋胜率相对推荐变化 {delta_pp:+.2f} 个百分点。" if delta_pp is not None else "胜率变化不可用。"
    return text


def current_summary(color: str, best: str | None, score: float | None, winrate: float | None) -> str:
    player = "黑" if color == "B" else "白"
    score_text = f"{score:+.2f} 目" if score is not None else "不可用"
    rate_text = f"{winrate * 100:.1f}%" if winrate is not None else "不可用"
    return f"记录末尾轮到{player}棋；推荐 {best or '不可用'}；{player}棋目差 {score_text}，胜率 {rate_text}。"


def review_summary(coverage: CoverageResult, count: int, status: str) -> str:
    text = f"已获得 {coverage.moves_evaluated}/{coverage.moves_total} 手的目损评估，检出 {count} 手明显失误。"
    if status == "partial":
        return text + "报告不完整；未评估部分不能视为没有失误。"
    if count == 0:
        return text + "按当前阈值，已记录的着手中未发现明显失误。"
    return text


def generate_review_report(review: ReviewResult) -> str:
    game, method, coverage = review.game_summary, review.method, review.coverage
    record_note = ("未完或结果未知，仅分析已记录的着手。" if game.record_status == "unfinished_or_unknown"
                   else "结果来自棋谱记录，不保证着手记录完整。")
    lines = [
        "对局简报", f"- {game.players['black']}（黑） vs {game.players['white']}（白）",
        f"- {game.board_size}x{game.board_size}；{'中国规则' if game.rules == 'chinese' else '日韩规则'}；贴目 {game.komi:g}",
        f"- 记录结果：{game.result or '未知'}。{record_note}", f"- {review.summary}",
        f"- 胜率变化覆盖 {coverage.moves_with_winrate}/{coverage.moves_total} 手。",
        f"- 判定：估计损失 >= {method.loss_threshold:g} 目为明显失误，>= {method.severe_threshold:g} 目为严重失误；摘要最多 {method.top_limit} 手。",
        f"- {method.note}", "", "重点失误",
    ]
    if not review.selected_mistakes:
        lines.append("暂无可列出的明显失误。" if review.status == "complete" else "可用证据中暂无可列出的明显失误；这不是完整的无失误结论。")
    for item in review.selected_mistakes:
        lines.append(f"- [{item.severity_label}] {item.summary}")
        lines.append(f"  推荐变化：{item.pv_summary or '不可用'}")
        lines.extend(f"  注意：{note}" for note in item.quality_notes)
    lines.extend(["", "分析来源", f"- {review.engine_source}"])
    evidence = review.current_position.evidence
    if evidence:
        lines.extend([
            f"- KataGo {evidence.engine_version}；模型 {evidence.model_id}；maxVisits={evidence.max_visits}",
            f"- 模型 SHA-256：{evidence.model_sha256}", f"- 配置 SHA-256：{evidence.config_sha256}",
        ])
    lines.extend(f"- {note}" for note in review.quality_notes)
    if "first_variation_only" in game.input_warnings:
        lines.append("- 棋谱包含变化分支，本次仅分析第一条主线。")
    if coverage.missing_move_numbers:
        lines.append("- 目损证据不足的手数：" + ", ".join(map(str, coverage.missing_move_numbers)))
    return "\n".join(lines)
