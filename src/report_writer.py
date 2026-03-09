from __future__ import annotations

from collections import Counter

from src.chinese_explanations import (
    final_training_note_cn,
    issue_label_cn,
    training_intro_cn,
)
from src.classifier import ClassifiedMistake
from src.review_result import ReviewResult
from src.sgf_parser import ParsedGame
from src.user_facing_labels import (
    category_interpretation,
    category_label,
    category_training_suggestion,
)


def generate_review_report(
    game: ParsedGame,
    mistakes: list[ClassifiedMistake],
    review: ReviewResult | None = None,
) -> str:
    sections = [
        _game_summary(game, mistakes),
        _review_summary(review),
        _positive_highlights(review),
        _top_mistakes(game.board_size, mistakes),
        _mistake_explanations(game.board_size, mistakes, review),
        _training_suggestions(mistakes),
    ]
    return "\n\n".join(section for section in sections if section)


def _game_summary(game: ParsedGame, mistakes: list[ClassifiedMistake]) -> str:
    komi = f"{game.komi:.1f}" if game.komi is not None else "未知"
    black = game.black_player or "未知黑棋"
    white = game.white_player or "未知白棋"
    result = game.result or "未知"
    lines = [
        "对局概况",
        f"- 棋盘：{game.board_size}x{game.board_size}",
        f"- 贴目：{komi}",
        f"- 对局者：{black}（黑） vs {white}（白）",
        f"- 结果：{result}",
        f"- 分析手数：{len(game.moves)}",
        f"- 重点复盘：{len(mistakes)}手",
    ]
    return "\n".join(lines)


def _review_summary(review: ReviewResult | None) -> str:
    if review is None:
        return ""

    summary = review.key_points.review_summary
    lines = [
        "整局总结",
        f"- 总评：{summary.summary}",
        f"- 布局：{summary.opening}",
        f"- 中盘：{summary.middle_game}",
        f"- 官子：{summary.endgame}",
        f"- 胜负主因：{issue_label_cn(summary.loss_cause)}",
    ]
    if summary.main_turning_points:
        lines.append("- 关键转折：")
        lines.extend(f"  - {item}" for item in summary.main_turning_points)
    return "\n".join(lines)


def _top_mistakes(board_size: int, mistakes: list[ClassifiedMistake]) -> str:
    lines = ["重点手"]
    if not mistakes:
        lines.append("- 目前阈值下，没有筛出需要重点复盘的失误。")
        return "\n".join(lines)

    for idx, mistake in enumerate(mistakes, start=1):
        lines.append(
            f"{idx}. {_move_ref(mistake.move_number)}："
            f"实战{_format_move(mistake.played_move, board_size)}，"
            f"推荐{_format_move(mistake.recommended_move, board_size)}，"
            f"损失{mistake.estimated_loss:.2f}目，"
            f"{category_label(mistake.category)}"
        )
    return "\n".join(lines)


def _positive_highlights(review: ReviewResult | None) -> str:
    if review is None:
        return ""

    highlights = [
        item
        for item in review.timeline
        if item.teaching_label in {"好手", "关键好手", "胜负手"}
    ]
    if not highlights:
        return ""

    priority = {"胜负手": 3, "关键好手": 2, "好手": 1}
    highlights.sort(
        key=lambda item: (
            -priority.get(item.teaching_label or "", 0),
            -(item.score_after - item.score_before),
            item.move_number,
        )
    )

    lines = ["亮点手"]
    for idx, item in enumerate(highlights[:3], start=1):
        lines.append(
            f"{idx}. {_move_ref(item.move_number)}："
            f"{item.teaching_label}，"
            f"实战{item.played_move.display}，"
            f"局势好转，"
            f"目数收益约{max(0.0, item.score_after - item.score_before):.2f}目。"
        )
    return "\n".join(lines)


def _mistake_explanations(
    board_size: int,
    mistakes: list[ClassifiedMistake],
    review: ReviewResult | None,
) -> str:
    lines = ["逐手说明"]
    if not mistakes:
        lines.append("目前没有可展开说明的重点失误。")
        return "\n".join(lines)

    explanations = {item.move_number: item for item in review.explanations} if review else {}
    for mistake in mistakes:
        lines.extend(_explanation_block(board_size, mistake, explanations.get(mistake.move_number)))
    return "\n".join(lines)


def _explanation_block(
    board_size: int,
    mistake: ClassifiedMistake,
    explanation,
) -> list[str]:
    default_summary = (
        f"实战下了{_format_move(mistake.played_move, board_size)}，"
        f"更好的选择是{_format_move(mistake.recommended_move, board_size)}，"
        f"这一手损失{mistake.estimated_loss:.2f}目。"
    )
    default_why = category_interpretation(mistake.category)
    title = explanation.title if explanation else f"{_move_ref(mistake.move_number)}（{category_label(mistake.category)}）"
    summary = explanation.summary if explanation else default_summary
    why = explanation.why_this_matters if explanation else default_why
    return [
        f"- {title}",
        f"  {summary}",
        f"  这手的问题：{why}",
    ]


def _training_suggestions(mistakes: list[ClassifiedMistake]) -> str:
    lines = ["训练建议"]
    if not mistakes:
        lines.append("- 先继续积累对局，等样本更多时再看共性问题。")
        return "\n".join(lines)

    counts = Counter(item.category for item in mistakes)
    lines.append(f"- {training_intro_cn()}")
    for category, _count in counts.most_common(2):
        lines.append(f"- {category_label(category)}：{category_training_suggestion(category)}")
    lines.append(f"- {final_training_note_cn()}")
    return "\n".join(lines)


def _format_move(move: str | None, board_size: int) -> str:
    if move is None:
        return "停一手"

    coord = _sgf_to_human_coord(move, board_size)
    if coord is None:
        return move
    return coord


def _move_ref(move_number: int) -> str:
    color = "黑" if move_number % 2 == 1 else "白"
    return f"{color}第{move_number}手"


def _sgf_to_human_coord(move: str, board_size: int) -> str | None:
    if len(move) != 2 or board_size <= 0:
        return None

    x = ord(move[0]) - ord("a")
    y = ord(move[1]) - ord("a")
    if x < 0 or y < 0 or x >= board_size or y >= board_size:
        return None

    column = _go_column_label(x)
    row = board_size - y
    return f"{column}{row}"


def _go_column_label(index: int) -> str:
    label_index = index
    if index >= 8:
        label_index += 1
    return chr(ord("A") + label_index)
