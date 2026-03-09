from __future__ import annotations

from src.classifier import MistakeCategory
from src.mistake_severity import MistakeSeverity


def phase_label_cn(phase: str) -> str:
    labels = {
        "opening": "布局",
        "middle_game": "中盘",
        "endgame": "官子",
    }
    return labels.get(phase, phase)


def issue_label_cn(issue: str) -> str:
    labels = {
        "balance": "形势判断",
        "fighting": "接触战",
        "endgame_loss": "官子",
    }
    return labels.get(issue, issue)


def phase_overview_text(phase: str, loss: float) -> str:
    phase_cn = phase_label_cn(phase)
    if loss < 0.5:
        return f"{phase_cn}阶段整体平稳，基本没有明显损失。"
    if loss < 1.5:
        return f"{phase_cn}阶段大体平稳，但有零星可惜之处，累计损失约{loss:.2f}目。"
    if loss < 3.0:
        return f"{phase_cn}阶段开始出现松动，累计损失约{loss:.2f}目。"
    return f"{phase_cn}阶段问题比较集中，累计损失约{loss:.2f}目。"


def current_position_explanation_cn(
    *,
    next_player: str,
    best_move: str,
    score_estimate: float,
    winrate: float,
) -> str:
    color = "黑棋" if next_player == "B" else "白棋"
    return (
        f"现在轮到{color}。KataGo建议走{best_move}，"
        f"目差预计为{score_estimate:.1f}，胜率约{winrate:.0%}。"
    )


def move_color_label_cn(color: str) -> str:
    if color == "B":
        return "黑"
    if color == "W":
        return "白"
    return ""


def move_ref_cn(color: str, move_number: int) -> str:
    color_label = move_color_label_cn(color)
    if color_label:
        return f"{color_label}第{move_number}手"
    return f"第{move_number}手"


def turning_point_summary_cn(
    *,
    color: str,
    move_number: int,
    phase: str,
    score_loss: float,
    winrate_delta: float,
) -> str:
    move_ref = move_ref_cn(color, move_number)
    return (
        f"{move_ref}是{phase_label_cn(phase)}阶段的重要转折点，"
        f"{_swing_summary_cn(score_loss=score_loss, winrate_delta=winrate_delta)}"
    )


def plan_break_summary_cn(
    *,
    anchor_move_number: int,
    color: str,
    break_move_number: int,
    expected_follow_up: str,
    played_move: str,
    score_loss: float,
) -> str:
    move_ref = move_ref_cn(color, break_move_number)
    variants = (
        (
            f"从第{anchor_move_number}手开始，前几手的处理思路已经比较清楚。"
            f"到了{move_ref}，原本更该接着走{expected_follow_up}，"
            f"实战却下成{played_move}，没有接上前面的思路，{_score_change_cn(score_loss)}。"
        ),
        (
            f"前面几手的重点到第{anchor_move_number}手后已经逐渐明朗，"
            f"{move_ref}这里本来应继续按{expected_follow_up}处理，"
            f"实战却下成{played_move}，局部判断有些脱节，{_score_change_cn(score_loss)}。"
        ),
        (
            f"这一段原本的主线已经形成，{move_ref}更合拍的下法是{expected_follow_up}。"
            f"实战改下{played_move}，问题不在于离开局部，而在于没有把前面的处理接上，"
            f"因此{_score_change_cn(score_loss)}。"
        ),
    )
    return variants[break_move_number % len(variants)]


def leave_main_battlefield_summary_cn(
    *,
    anchor_move_number: int,
    color: str,
    break_move_number: int,
    expected_follow_up: str,
    played_move: str,
    score_loss: float,
) -> str:
    move_ref = move_ref_cn(color, break_move_number)
    variants = (
        (
            f"从第{anchor_move_number}手开始，这一带已经是当前最要紧的主战场。"
            f"到了{move_ref}，推荐仍然集中在这里，原本更该走{expected_follow_up}，"
            f"实战却下成{played_move}，等于脱离了主战场，{_score_change_cn(score_loss)}。"
        ),
        (
            f"当前最重要的战斗还在这一带，{move_ref}本来该继续用{expected_follow_up}应对。"
            f"实战却转去下{played_move}，把焦点移到了别处，节奏上有些脱离主战场，"
            f"{_score_change_cn(score_loss)}。"
        ),
        (
            f"这里前面的攻守还没有告一段落，推荐主线也一直围着这一块展开。"
            f"{move_ref}若走{expected_follow_up}才是正着，实战却下成{played_move}，"
            f"更大的问题是离开了当前真正该处理的主战场，{_score_change_cn(score_loss)}。"
        ),
    )
    return variants[break_move_number % len(variants)]


def phase_summary_cn(*, biggest_problem_phase: str, main_issue: str) -> str:
    return (
        f"全局看，损失主要集中在{phase_label_cn(biggest_problem_phase)}，"
        f"主因是{issue_label_cn(main_issue)}。"
    )


def review_summary_total_cn(
    *,
    main_issue: str,
    biggest_problem_phase: str,
    turning_point_count: int,
) -> str:
    return (
        f"这盘棋的胜负手主要出现在{phase_label_cn(biggest_problem_phase)}，"
        f"核心问题是{issue_label_cn(main_issue)}。"
        f"全局最值得回看的关键点共有{turning_point_count}处。"
    )


def explanation_title_cn(move_number: int, color: str, category_label: str) -> str:
    return f"{move_ref_cn(color, move_number)}（{category_label}）"


def explanation_summary_cn(
    *,
    move_number: int,
    color: str,
    phase: str,
    played_move: str,
    recommended_move: str,
    score_loss: float,
    winrate_delta: float,
    severity_label: str,
    is_turning_point: bool,
) -> str:
    opening = "这是本局关键处之一。" if is_turning_point else "这一手值得重点复盘。"
    move_ref = move_ref_cn(color, move_number)
    return (
        f"{opening}{phase_label_cn(phase)}阶段的{move_ref}，"
        f"实战下了{played_move}，更稳妥的下法是{recommended_move}。"
        f"这一手属于{severity_label}，{_swing_summary_cn(score_loss=score_loss, winrate_delta=winrate_delta)}"
    )


def explanation_why_cn(
    *,
    move_number: int,
    category: MistakeCategory,
    phase: str,
    plan_break_note: bool,
    leave_main_battlefield_note: bool,
) -> str:
    base = category_interpretation_cn(category)
    if leave_main_battlefield_note:
        variants = (
            f"{base} 当前主战场还在这里，实战却转到了别处，节奏上有些脱离主战场。",
            f"{base} 这一手把焦点从当前最重要的战斗区域移开了，前面的攻守没有继续下去。",
            f"{base} 这里更大的问题不是手法本身，而是离开了当前真正该处理的主战场。",
        )
        return variants[move_number % len(variants)]
    if plan_break_note:
        variants = (
            f"{base} 这一步没有顺着前面的处理思路继续，局部判断有些脱节。",
            f"{base} 前面几手的重点已经比较清楚，但这一手的处理没有接上。",
            f"{base} 这里的问题不在于离开局部，而在于局部的下法没有延续前面的主线。",
        )
        return variants[move_number % len(variants)]
    return f"{base} 问题主要发生在{phase_label_cn(phase)}。"


def _score_change_cn(score_loss: float) -> str:
    if score_loss <= -0.05:
        return f"收益约{abs(score_loss):.2f}目"
    if score_loss < 0.05:
        return "目数变化不大"
    return f"损失约{score_loss:.2f}目"


def _winrate_change_cn(winrate_delta: float) -> str:
    if winrate_delta >= 0.005:
        return f"胜率提升{winrate_delta:.0%}"
    if winrate_delta <= -0.005:
        return f"胜率下滑{abs(winrate_delta):.0%}"
    return "胜率变化不大"


def _swing_summary_cn(*, score_loss: float, winrate_delta: float) -> str:
    if score_loss <= -0.05 or winrate_delta >= 0.005:
        return f"这一手带来{_score_change_cn(score_loss)}，{_winrate_change_cn(winrate_delta)}。"
    if score_loss < 0.05 and abs(winrate_delta) < 0.005:
        return "这一手目数和胜率都没有明显变化。"
    return f"这一手造成{_score_change_cn(score_loss)}，{_winrate_change_cn(winrate_delta)}。"


def category_interpretation_cn(category: MistakeCategory) -> str:
    labels: dict[MistakeCategory, str] = {
        "direction_error": "这手多半是大方向选边不够理想，先后次序有些偏。",
        "local_overplay": "这手在局部有点发力过猛，效率不够高。",
        "defensive_overreaction": "这手并非不能下，但明显偏稳，给对手让出了主动。",
        "endgame_loss": "这手官子价值偏低，漏掉了更大的先手或实地。",
        "tactical_blunder": "这手主要是具体计算没有跟上，战术上吃了亏。",
        "unclear": "这手的信号不算单一，但从结果看还是明显亏了。",
    }
    return labels[category]


def category_training_suggestion_cn(category: MistakeCategory) -> str:
    labels: dict[MistakeCategory, str] = {
        "direction_error": "复盘时先比一比双方大场与拆边方向，训练先后次序的判断。",
        "local_overplay": "多练习接触战里“见好就收”的选择，别每一手都想着继续压。",
        "defensive_overreaction": "多看主动出头、轻灵处理的例子，减少只顾补棋的惯性。",
        "endgame_loss": "每盘棋后做几道官子大小判断，把先手价值先算清楚。",
        "tactical_blunder": "把死活和对杀题重新捡起来，重点练短算与手顺确认。",
        "unclear": "这类棋形先不要急着下结论，复盘时把实战和推荐变化摆一遍再判断。",
    }
    return labels[category]


def training_intro_cn() -> str:
    return "这盘棋后续训练可以先抓下面两点："


def final_training_note_cn() -> str:
    return "下次复盘时，先自己判断实战手和推荐手的差别，再看文字说明，进步会更快。"


def severity_label_cn(severity: MistakeSeverity) -> str:
    labels: dict[MistakeSeverity, str] = {
        "inaccuracy": "可商榷",
        "mistake": "问题手",
        "major_mistake": "明显失误",
        "blunder": "大失误",
    }
    return labels[severity]
