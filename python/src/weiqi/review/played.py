"""Restricted searches of played moves for the same-root diagnostic
(MIGRATION E04, ADR-P02).

After the free analysis of a game, `weiqi.metrics.played_moves_to_search`
names the turns whose played move got no value; each is searched again with
the first move limited to the played one. The searches go through the cached
analyzer, so a repeated review asks the engine nothing, and they are sent
together: the engine process works on as many queries at once as its
settings allow.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from weiqi.metrics import Evaluations, played_moves_to_search

if TYPE_CHECKING:
    from weiqi.engine import CachedAnalysis, CachedAnalyzer


async def search_played_moves(
    analyzer: CachedAnalyzer,
    evaluations: Evaluations,
    *,
    timeout: float | None = None,
) -> tuple[CachedAnalysis, ...]:
    """The restricted searches that the same-root values of `evaluations`
    need, in turn order; pass them to `weiqi.metrics.move_metrics`."""
    request = evaluations.request
    turns = played_moves_to_search(evaluations)
    searches = [
        analyzer.analyze(request.played_move_search(turn), timeout=timeout) for turn in turns
    ]
    return tuple(await asyncio.gather(*searches))
