from __future__ import annotations

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
    "direction_error": "This likely chose the wrong side or direction of play.",
    "local_overplay": "This likely pushed too hard in a local fight.",
    "defensive_overreaction": "This looks playable, but likely more cautious than needed.",
    "endgame_loss": "This likely missed available endgame points.",
    "tactical_blunder": "This likely missed a concrete tactical detail.",
    "unclear": "Engine signals are mixed, so this pattern is not yet clear.",
}

_CATEGORY_TRAINING: dict[MistakeCategory, str] = {
    "direction_error": "Review opening direction principles and compare side choices.",
    "local_overplay": "Practice choosing calmer local continuations in fighting positions.",
    "defensive_overreaction": "Review examples where active play is stronger than pure safety.",
    "endgame_loss": "Do short endgame counting drills before each game session.",
    "tactical_blunder": "Do a focused life-and-death and reading exercise set.",
    "unclear": "Recheck this position manually because the pattern is not conclusive.",
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
