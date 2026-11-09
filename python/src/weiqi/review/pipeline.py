"""One whole review of one game (MIGRATION R08): the whole-game analysis with
ownership, the restricted searches of played moves, then the result built
from that evidence. Every engine call goes through the cached analyzer, so a
repeated review asks the engine nothing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from weiqi.review.game_input import GameInput, review_request
from weiqi.review.played import search_played_moves
from weiqi.review.result import ReviewResult, ReviewSettings, build_result

if TYPE_CHECKING:
    from weiqi.engine import CachedAnalysis, CachedAnalyzer, TurnResult


@dataclass(frozen=True, slots=True)
class Review:
    """A finished review and the evidence it was built from."""

    result: ReviewResult
    analysis: CachedAnalysis
    played_searches: tuple[CachedAnalysis, ...]

    @property
    def cached_turns(self) -> int:
        """Turns answered from the store, over all queries of this review."""
        return sum(len(a.cached_turns) for a in (self.analysis, *self.played_searches))

    @property
    def engine_turns(self) -> int:
        """Turns the engine analysed for this review."""
        return sum(
            len(a.engine_analysis.results)
            for a in (self.analysis, *self.played_searches)
            if a.engine_analysis is not None
        )


async def review_game(
    analyzer: CachedAnalyzer,
    game: GameInput,
    rules: str,
    komi: float,
    settings: ReviewSettings | None = None,
    *,
    on_turn: Callable[[TurnResult], None] | None = None,
    timeout: float | None = None,
) -> Review:
    """Reviews `game` under confirmed `rules` and `komi`.

    `on_turn` reports progress of the whole-game analysis, one call per
    turn; the played-move searches that follow are short and not reported.
    """
    settings = settings or ReviewSettings()
    request = review_request(
        game, rules, komi, max_visits=settings.max_visits, pv_length=settings.pv_length
    )
    analysis = await analyzer.analyze(request, on_turn=on_turn, timeout=timeout)
    searches = await search_played_moves(analyzer, analysis, timeout=timeout)
    return Review(build_result(game, analysis, searches, settings), analysis, searches)
