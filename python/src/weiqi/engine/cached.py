"""Exact reuse of stored results before asking the engine (ARCHITECTURE §5.3, ADR-P03).

`CachedAnalyzer` computes each requested turn's `query_key`, takes the turns
already in a `ResultStore`, sends only the others to the engine in one
query, and stores what the engine returns. A stored result is reused only
when the whole key matches: same engine identity and the same search at
that turn, so reuse never changes a result.

The engine layer defines the store's interface; the storage layer
implements it, so this module never touches a database.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

from weiqi.engine.errors import EngineUnavailableError

if TYPE_CHECKING:
    from weiqi.engine.client import GameAnalysis, KataGoEngine, TurnResult
    from weiqi.engine.identity import EngineIdentity
    from weiqi.engine.request import AnalysisRequest


class ResultStore(Protocol):
    """Where analysed turns are kept, by `query_key`."""

    async def load(self, query_keys: Sequence[str]) -> dict[str, TurnResult]:
        """The stored results among `query_keys`; unknown keys are left out."""
        ...

    async def save(self, analysis: GameAnalysis) -> None:
        """Stores every turn of `analysis`; a key already stored is kept as is."""
        ...


@dataclass(frozen=True, slots=True)
class CachedAnalysis:
    """The answer to one request, partly or wholly from the store."""

    request: AnalysisRequest
    identity: EngineIdentity
    results: tuple[TurnResult, ...]
    """One per `request.analyze_turns`, in that order."""
    cached_turns: tuple[int, ...]
    """Turns answered from the store without asking the engine."""
    engine_analysis: GameAnalysis | None
    """The engine query for the other turns, or `None` if there were none."""


class CachedAnalyzer:
    """A `KataGoEngine` in front of which a `ResultStore` answers what it can."""

    def __init__(self, engine: KataGoEngine, store: ResultStore) -> None:
        self._engine = engine
        self._store = store
        self._hits = 0
        self._misses = 0

    @property
    def hits(self) -> int:
        """Turns answered from the store so far."""
        return self._hits

    @property
    def misses(self) -> int:
        """Turns sent to the engine so far."""
        return self._misses

    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        timeout: float | None = None,
        on_turn: Callable[[TurnResult], None] | None = None,
    ) -> CachedAnalysis:
        """Analyses every turn of `request`, reusing stored turns.

        `on_turn` sees stored turns first, then engine turns as they arrive.
        Results are stored only when the engine query completes.
        """
        # The identity is part of every key, so the engine must report it first.
        identity = await self._engine.start()
        keys = {turn: request.query_key(identity, turn) for turn in request.analyze_turns}
        stored = await self._store.load(list(keys.values()))
        cached = tuple(turn for turn in request.analyze_turns if keys[turn] in stored)
        missing = tuple(turn for turn in request.analyze_turns if keys[turn] not in stored)
        self._hits += len(cached)
        self._misses += len(missing)

        results = {turn: stored[keys[turn]] for turn in cached}
        if on_turn is not None:
            for turn in cached:
                on_turn(results[turn])
        engine_analysis = None
        if missing:
            engine_analysis = await self._engine.analyze(
                replace(request, analyze_turns=missing), timeout=timeout, on_turn=on_turn
            )
            await self._store.save(engine_analysis)
            if engine_analysis.identity != identity:
                # A restart in between loaded different files; the new results
                # are stored under their own keys, but they cannot be mixed
                # with results keyed by the old identity.
                raise EngineUnavailableError(
                    "engine_changed", "the engine changed during the analysis; retry"
                )
            results.update((r.analysis.turn, r) for r in engine_analysis.results)
        return CachedAnalysis(
            request=request,
            identity=identity,
            results=tuple(results[turn] for turn in request.analyze_turns),
            cached_turns=cached,
            engine_analysis=engine_analysis,
        )
