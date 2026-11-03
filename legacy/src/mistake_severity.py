from __future__ import annotations

from typing import Literal

MistakeSeverity = Literal["mistake", "severe"]
DEFAULT_LOSS_THRESHOLD = 3.0
DEFAULT_SEVERE_THRESHOLD = 5.0
MAX_REVIEW_MISTAKES = 5


def severity_from_loss(
    score_loss: float | None,
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> MistakeSeverity | None:
    if score_loss is None or score_loss <= 0 or score_loss < loss_threshold:
        return None
    return "severe" if score_loss >= severe_threshold else "mistake"


def severity_label(severity: MistakeSeverity | None) -> str | None:
    return {"mistake": "明显失误", "severe": "严重失误"}.get(severity)
