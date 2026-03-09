from __future__ import annotations

from src.chinese_explanations import (
    category_interpretation_cn,
    category_training_suggestion_cn,
)
from src.classifier import MistakeCategory
from src.mistake_severity import MistakeSeverity

_CATEGORY_LABELS: dict[MistakeCategory, str] = {
    "direction_error": "方向判断问题",
    "local_overplay": "局部用力过猛",
    "defensive_overreaction": "防守过度",
    "endgame_loss": "官子亏损",
    "tactical_blunder": "计算失误",
    "unclear": "暂难归类",
}

_SEVERITY_LABELS: dict[MistakeSeverity, str] = {
    "inaccuracy": "可商榷",
    "mistake": "问题手",
    "major_mistake": "明显失误",
    "blunder": "大失误",
}

_CATEGORY_INTERPRETATION: dict[MistakeCategory, str] = {
    "direction_error": category_interpretation_cn("direction_error"),
    "local_overplay": category_interpretation_cn("local_overplay"),
    "defensive_overreaction": category_interpretation_cn("defensive_overreaction"),
    "endgame_loss": category_interpretation_cn("endgame_loss"),
    "tactical_blunder": category_interpretation_cn("tactical_blunder"),
    "unclear": category_interpretation_cn("unclear"),
}

_CATEGORY_TRAINING: dict[MistakeCategory, str] = {
    "direction_error": category_training_suggestion_cn("direction_error"),
    "local_overplay": category_training_suggestion_cn("local_overplay"),
    "defensive_overreaction": category_training_suggestion_cn("defensive_overreaction"),
    "endgame_loss": category_training_suggestion_cn("endgame_loss"),
    "tactical_blunder": category_training_suggestion_cn("tactical_blunder"),
    "unclear": category_training_suggestion_cn("unclear"),
}

_CATEGORY_ORDER: tuple[MistakeCategory, ...] = (
    "direction_error",
    "local_overplay",
    "defensive_overreaction",
    "endgame_loss",
    "tactical_blunder",
    "unclear",
)


def category_label(category: MistakeCategory) -> str:
    return _CATEGORY_LABELS[category]


def severity_label(severity: MistakeSeverity) -> str:
    return _SEVERITY_LABELS[severity]


def category_interpretation(category: MistakeCategory) -> str:
    return _CATEGORY_INTERPRETATION[category]


def category_training_suggestion(category: MistakeCategory) -> str:
    return _CATEGORY_TRAINING[category]


def ordered_categories() -> tuple[MistakeCategory, ...]:
    return _CATEGORY_ORDER
