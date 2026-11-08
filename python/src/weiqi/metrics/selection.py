"""Choosing and ranking mistakes (MIGRATION R03, R04; ADR-004).

Moves are ranked by unrounded loss, largest first, then by move number. The
list is never padded to reach a count; a limit only shortens it, and the
full chronological metrics stay available to callers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from weiqi.metrics.errors import MetricInputError
from weiqi.metrics.loss import MoveMetrics
from weiqi.metrics.severity import DEFAULT_BAND, Severity, SeverityBand


@dataclass(frozen=True, slots=True)
class Mistake:
    """A move whose loss reaches a severity threshold."""

    metrics: MoveMetrics
    definition: str
    score_loss: float
    severity: Severity


def select_mistakes(
    metrics: Iterable[MoveMetrics],
    band: SeverityBand = DEFAULT_BAND,
    *,
    limit: int | None = None,
    definition: Literal["sequential", "same_root"] = "sequential",
) -> tuple[Mistake, ...]:
    """Mistakes by `definition` under `band`, ranked; at most `limit` of them.

    `sequential` is the primary definition (ADR-P02); `same_root` exists for
    the diagnostic view and the comparison with legacy.
    """
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise MetricInputError("invalid_limit", "limit must be a positive integer or None")
    chosen: list[Mistake] = []
    for item in metrics:
        estimate = item.sequential if definition == "sequential" else item.same_root
        loss = estimate.score_loss
        severity = band.classify(loss)
        if severity is not None and loss is not None:
            chosen.append(Mistake(item, estimate.definition, loss, severity))
    chosen.sort(key=lambda mistake: (-mistake.score_loss, mistake.metrics.move_number))
    return tuple(chosen if limit is None else chosen[:limit])
