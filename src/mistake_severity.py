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
    *,
    winrate_delta: float = 0.0,
    winrate_before: float | None = None,
    winrate_after: float | None = None,
) -> MistakeSeverity:
    abs_winrate_delta = abs(winrate_delta)

    if (
        score_loss >= thresholds.blunder
        or abs_winrate_delta >= 0.30
        or _is_nearly_losing_transition(winrate_before, winrate_after, minimum_drop=0.25)
    ):
        return "blunder"
    if (
        score_loss >= thresholds.major_mistake
        or abs_winrate_delta >= 0.18
        or _is_nearly_losing_transition(winrate_before, winrate_after, minimum_drop=0.18)
    ):
        return "major_mistake"
    if score_loss >= thresholds.mistake or abs_winrate_delta >= 0.10:
        return "mistake"
    return "inaccuracy"


def _is_nearly_losing_transition(
    winrate_before: float | None,
    winrate_after: float | None,
    *,
    minimum_drop: float,
) -> bool:
    if winrate_before is None or winrate_after is None:
        return False
    return (
        winrate_before >= 0.45
        and winrate_after <= 0.20
        and (winrate_before - winrate_after) >= minimum_drop
    )
