"""An analysis request: one game, the turns to analyse, and the search settings.

Building a request replays it through the Rust rules core, so the board
size, rules, komi, setup stones and every move are checked by the one rules
authority before anything reaches the engine. The replay also fixes which
player is to move at each turn, which the response parser checks.

`query_key` is the exact-reuse cache key of DECISIONS ADR-P03: the SHA-256
of a canonical JSON document holding the engine identity and everything
that determines the search at one turn.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import weiqi_core

from weiqi.engine.errors import InvalidRequestError

if TYPE_CHECKING:
    from weiqi_core import Color, Move, Point

    from weiqi.engine.identity import EngineIdentity

type JsonScalar = bool | int | float | str

# Bump when the canonical document changes, so old keys can never match.
QUERY_KEY_VERSION = 1
MAX_VISITS_LIMIT = 100_000
MAX_PV_LENGTH = 60


def check_settings(
    settings: Iterable[tuple[str, JsonScalar]] | Mapping[str, JsonScalar],
) -> tuple[tuple[str, JsonScalar], ...]:
    """Engine settings as a sorted tuple, rejecting values JSON cannot carry exactly."""
    items = settings.items() if isinstance(settings, Mapping) else settings
    result: dict[str, JsonScalar] = {}
    for name, value in items:
        if not isinstance(name, str) or not name:
            raise InvalidRequestError("invalid_setting", "setting names must be non-empty strings")
        if name in result:
            raise InvalidRequestError("invalid_setting", f"setting {name!r} given twice")
        if not isinstance(value, bool | int | float | str) or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            raise InvalidRequestError("invalid_setting", f"setting {name!r} has an invalid value")
        result[name] = value
    return tuple(sorted(result.items()))


def _whole_number(value: object, name: str, low: int, high: int) -> int:
    # bool is an int subclass; True must not pass as 1.
    if type(value) is not int or not low <= value <= high:
        raise InvalidRequestError(f"invalid_{name}", f"{name} must be an integer in {low}..{high}")
    return value


def canonical_json(document: object) -> str:
    """The one JSON text of `document` that the project hashes."""
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """A whole game sent as one KataGo query, answered once per analysed turn.

    Turn 0 is the starting position and turn n the position after
    `moves[n - 1]`, as in KataGo's `analyzeTurns`.
    """

    width: int
    height: int
    rules: str
    """A rule-set name that both the core and KataGo accept, e.g. "japanese"."""
    komi: float
    moves: tuple[tuple[Color, Move], ...]
    analyze_turns: tuple[int, ...]
    max_visits: int
    pv_length: int = 8
    include_ownership: bool = False
    initial_black: tuple[Point, ...] = ()
    initial_white: tuple[Point, ...] = ()
    initial_player: Color = "B"
    override_settings: tuple[tuple[str, JsonScalar], ...] = ()
    allow_move: Move | None = None
    """If set, the search at the one analysed turn may only play this move
    first (KataGo `allowMoves` with `untilDepth` 1); see `played_move_search`."""
    players: tuple[Color, ...] = field(init=False, repr=False, compare=False)
    """The player to move at each turn 0..len(moves), from the core's replay."""
    hashes: tuple[tuple[int, int], ...] = field(init=False, repr=False, compare=False)
    """`(stones_hash, situation_hash)` of each turn 0..len(moves), from the
    core (ZOBRIST_VERSION); a position index, never a cache key (ADR-P03)."""

    def __post_init__(self) -> None:
        if isinstance(self.komi, bool) or not isinstance(self.komi, int | float):
            raise InvalidRequestError("invalid_komi", "komi must be a number")
        set_ = object.__setattr__  # the dataclass is frozen; normalise once here
        set_(self, "komi", float(self.komi))
        set_(self, "moves", tuple((color, move) for color, move in self.moves))
        set_(self, "initial_black", tuple(sorted(self.initial_black)))
        set_(self, "initial_white", tuple(sorted(self.initial_white)))
        _whole_number(self.max_visits, "max_visits", 1, MAX_VISITS_LIMIT)
        _whole_number(self.pv_length, "pv_length", 1, MAX_PV_LENGTH)
        if type(self.include_ownership) is not bool:
            raise InvalidRequestError("invalid_ownership_flag", "include_ownership must be a bool")
        set_(self, "override_settings", check_settings(self.override_settings))
        players, hashes = self._replay()
        set_(self, "players", players)
        set_(self, "hashes", hashes)

        turns = tuple(self.analyze_turns)
        set_(self, "analyze_turns", turns)
        last = len(self.moves)
        if (
            not turns
            or any(type(turn) is not int or not 0 <= turn <= last for turn in turns)
            or list(turns) != sorted(set(turns))
        ):
            raise InvalidRequestError(
                "invalid_turns", f"analyze_turns must be increasing turns in 0..{last}"
            )
        if self.allow_move is not None:
            if len(turns) != 1:
                raise InvalidRequestError(
                    "invalid_allow_move", "a restricted search analyses exactly one turn"
                )
            try:
                self._gtp(self.allow_move)
            except (weiqi_core.CoreError, TypeError, ValueError) as error:
                raise InvalidRequestError(
                    "invalid_allow_move", "allow_move must be a point on the board or a pass"
                ) from error

    def _replay(self) -> tuple[tuple[Color, ...], tuple[tuple[int, int], ...]]:
        """Replays the game in the core's record mode and returns who is to
        move at each turn and each turn's position hashes. Record mode
        applies recorded rule violations (as KataGo does) but rejects
        occupied or off-board points."""
        try:
            game = weiqi_core.Game(
                self.width,
                self.height,
                weiqi_core.Rules.from_name(self.rules),
                self.komi,
                weiqi_core.Setup(
                    list(self.initial_black), list(self.initial_white), self.initial_player
                ),
            )
            players = [game.to_play]
            position = game.position()
            hashes = [(position.stones_hash, position.situation_hash)]
            for color, move in self.moves:
                game.play_as(color, move, "record")
                players.append(game.to_play)
                position = game.position()
                hashes.append((position.stones_hash, position.situation_hash))
        except weiqi_core.CoreError as error:
            raise InvalidRequestError(error.code, str(error)) from error
        return tuple(players), tuple(hashes)

    def _gtp(self, move: Move) -> str:
        return weiqi_core.to_gtp(move, self.width, self.height)

    def _search_fields(self, turn: int) -> dict[str, object]:
        """Every query field that determines the search at `turn`."""
        return {
            "boardXSize": self.width,
            "boardYSize": self.height,
            "rules": self.rules,
            "komi": self.komi,
            "initialStones": [["B", self._gtp(p)] for p in self.initial_black]
            + [["W", self._gtp(p)] for p in self.initial_white],
            "initialPlayer": self.initial_player,
            "moves": [[color, self._gtp(move)] for color, move in self.moves[:turn]],
            "maxVisits": self.max_visits,
            "analysisPVLen": self.pv_length,
            "includeOwnership": self.include_ownership,
            "overrideSettings": dict(self.override_settings),
        }

    def _restriction(self, turn: int) -> dict[str, object]:
        """The `allowMoves` field at `turn`, or nothing for a free search.

        Left out entirely when unset, so free searches keep the keys they had
        before restricted searches existed.
        """
        if self.allow_move is None:
            return {}
        player = self.players[turn]
        return {
            "allowMoves": [
                {"player": player, "moves": [self._gtp(self.allow_move)], "untilDepth": 1}
            ]
        }

    def to_query(self, query_id: str) -> dict[str, object]:
        """The KataGo query object (one JSON line once serialised)."""
        return {
            "id": query_id,
            **self._search_fields(len(self.moves)),
            **self._restriction(self.analyze_turns[0]),
            "analyzeTurns": list(self.analyze_turns),
        }

    def played_move_search(self, turn: int) -> AnalysisRequest:
        """A search of the position at `turn` restricted to the move played
        there, `moves[turn]`, without ownership (MIGRATION E04).

        It gives the played move a full search budget when the free search
        considered it too little; the same-root diagnostic (ADR-P02) compares
        it with the free search's recommendation.
        """
        _whole_number(turn, "turn", 0, len(self.moves) - 1)
        return replace(
            self,
            analyze_turns=(turn,),
            include_ownership=False,
            allow_move=self.moves[turn][1],
        )

    def key_document(self, identity: EngineIdentity, turn: int) -> str:
        """The canonical JSON text that `query_key` hashes.

        Moves after `turn` do not affect the result at `turn`, so they are
        left out: two games with the same opening share keys for those turns.
        """
        _whole_number(turn, "turn", 0, len(self.moves))
        return canonical_json(
            {
                "format": QUERY_KEY_VERSION,
                "engine": identity.key_fields(),
                "search": {**self._search_fields(turn), **self._restriction(turn)},
            }
        )

    def query_key(self, identity: EngineIdentity, turn: int) -> str:
        """The exact-reuse key for the result at `turn` (ADR-P03)."""
        return hashlib.sha256(self.key_document(identity, turn).encode("utf-8")).hexdigest()
