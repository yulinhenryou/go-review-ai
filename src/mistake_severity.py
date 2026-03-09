from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MistakeSeverity = Literal[
    "inaccuracy",
    "mistake",
    "major_mistake",
    "blunder",
]


@dataclass(frozen=True)
class SeverityThresholds:
    inaccuracy: float = 0.7
    mistake: float = 1.5
    major_mistake: float = 3.0
    blunder: float = 5.0


DEFAULT_SEVERITY_THRESHOLDS = SeverityThresholds()


def severity_from_loss(
    score_loss: float,
    thresholds: SeverityThresholds = DEFAULT_SEVERITY_THRESHOLDS,
) -> MistakeSeverity:
    if score_loss >= thresholds.blunder:
        return "blunder"
    if score_loss >= thresholds.major_mistake:
        return "major_mistake"
    if score_loss >= thresholds.mistake:
        return "mistake"
    return "inaccuracy"
