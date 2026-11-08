"""Go (Weiqi / Baduk) rules, SGF parsing and position hashing from the Rust core.

Hand-written stub for the `weiqi-py` extension module; `mypy.stubtest`
checks it against the built module in CI. Every value returned is an owned
snapshot: changing a `Game` never changes a `Position` taken earlier.
"""

from typing import Final, Literal, final

type Color = Literal["B", "W"]
type Point = tuple[int, int]
"""`(x, y)`, zero-based from the top left."""
type Move = Point | Literal["pass"]
type Mode = Literal["strict", "record"]

ZOBRIST_VERSION: Final[int]
MAX_BOARD_SIZE: Final[int]

def to_gtp(move_: Move, width: int, height: int) -> str:
    """The GTP vertex of `move_`, e.g. "Q16" or "pass"; columns skip I."""

def from_gtp(vertex: str, width: int, height: int) -> Move:
    """The move a GTP vertex names; raises `CoreError` if it is malformed or off the board."""

class CoreError(ValueError):
    """Invalid input; `code` is the core's stable machine-readable code."""

    code: str

class IllegalMoveError(CoreError):
    """A move that was not applied."""

class SgfError(CoreError):
    """Bytes that are not SGF."""

    offset: int

class ExtractError(CoreError):
    """An SGF game tree that is not a playable game record."""

    node: int

class ReplayError(CoreError):
    """A game record whose setup or moves cannot be replayed."""

    move_number: int | None
    """1-based; `None` when the setup is invalid."""

@final
class Rules:
    """A rule set; build one with `Rules.from_name`."""

    @staticmethod
    def from_name(name: str) -> Rules:
        """The rule set KataGo calls `name`, e.g. "japanese" or "tromp-taylor"."""
    @property
    def ko(self) -> Literal["simple", "positional", "situational"]: ...
    @property
    def scoring(self) -> Literal["area", "territory"]: ...
    @property
    def tax(self) -> Literal["none", "seki", "all"]: ...
    @property
    def suicide(self) -> Literal["forbidden", "multi_stone_allowed"]: ...
    @property
    def button(self) -> bool: ...
    @property
    def white_handicap_bonus(self) -> Literal["0", "N", "N-1"]: ...
    @property
    def friendly_pass_ok(self) -> bool: ...
    def __eq__(self, other: object, /) -> bool: ...

@final
class Setup:
    """Stones before the first move and who moves first."""

    def __new__(
        cls, black: list[Point] = ..., white: list[Point] = ..., to_play: Color = "B"
    ) -> Setup: ...
    @property
    def black(self) -> list[Point]: ...
    @property
    def white(self) -> list[Point]: ...
    @property
    def to_play(self) -> Color: ...

@final
class Captures:
    """Stones of each color removed from the board."""

    @property
    def black(self) -> int: ...
    @property
    def white(self) -> int: ...
    def __eq__(self, other: object, /) -> bool: ...

@final
class Position:
    """An owned snapshot of a position."""

    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def cells(self) -> list[Color | None]:
        """Row-major from the top left: `cells[y * width + x]`."""
    @property
    def to_play(self) -> Color: ...
    @property
    def ko_ban(self) -> Point | None:
        """The point `to_play` may not play because of simple ko."""
    @property
    def captures(self) -> Captures: ...
    @property
    def consecutive_passes(self) -> int: ...
    @property
    def stones_hash(self) -> int:
        """128-bit hash of the stones and board size."""
    @property
    def situation_hash(self) -> int:
        """128-bit hash of the stones, player to move and ko ban."""

@final
class MoveEffect:
    """What an applied move changed."""

    @property
    def captured(self) -> list[Point]: ...
    @property
    def suicided(self) -> list[Point]: ...
    @property
    def repeated_position(self) -> bool: ...
    @property
    def violations(self) -> list[str]:
        """Rules broken by a move applied in "record" mode."""

@final
class Game:
    """A game in progress."""

    def __new__(
        cls, width: int, height: int, rules: Rules, komi: float, setup: Setup | None = None
    ) -> Game: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def rules(self) -> Rules: ...
    @property
    def komi(self) -> float: ...
    @property
    def to_play(self) -> Color: ...
    @property
    def move_count(self) -> int: ...
    def moves(self) -> list[tuple[Color, Move]]: ...
    def position(self) -> Position: ...
    def play(self, move: Move) -> MoveEffect:
        """Plays `move` for the player to move; raises `IllegalMoveError`."""
    def play_as(self, color: Color, move: Move, mode: Mode = "strict") -> MoveEffect:
        """Plays `move` for `color`; "record" mode applies rule violations."""
    def undo(self) -> tuple[Color, Move] | None:
        """Takes back the last move and returns it, or `None` at the start."""

@final
class SgfWarning:
    @property
    def code(self) -> str: ...
    @property
    def offset(self) -> int | None: ...

@final
class SgfTree:
    """One parsed game tree."""

    def to_sgf(self) -> str: ...
    def __len__(self) -> int: ...

@final
class Collection:
    """The games in an SGF file, with its decoding and warnings."""

    @property
    def games(self) -> list[SgfTree]: ...
    @property
    def encoding(self) -> str: ...
    @property
    def warnings(self) -> list[SgfWarning]: ...

@final
class GameInfo:
    @property
    def black_player(self) -> str | None: ...
    @property
    def white_player(self) -> str | None: ...
    @property
    def black_rank(self) -> str | None: ...
    @property
    def white_rank(self) -> str | None: ...
    @property
    def date(self) -> str | None: ...
    @property
    def event(self) -> str | None: ...
    @property
    def round(self) -> str | None: ...
    @property
    def place(self) -> str | None: ...
    @property
    def name(self) -> str | None: ...
    @property
    def result_text(self) -> str | None: ...

@final
class ExtractWarning:
    @property
    def code(self) -> str: ...
    @property
    def node(self) -> int | None: ...

@final
class GameRecord:
    """The main line of a game tree."""

    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def rules(self) -> Rules | None:
        """`None` when `RU` is missing or not recognized (see `rules_text`)."""
    @property
    def rules_text(self) -> str | None: ...
    @property
    def komi(self) -> float | None:
        """`None` when `KM` is missing or invalid."""
    @property
    def handicap(self) -> int | None: ...
    @property
    def setup(self) -> Setup: ...
    @property
    def moves(self) -> list[tuple[Color, Move]]: ...
    @property
    def info(self) -> GameInfo: ...
    @property
    def warnings(self) -> list[ExtractWarning]: ...
    def replay(self, rules: Rules, komi: float) -> Replay:
        """Replays the record in "record" mode; raises `ReplayError`."""

@final
class ReplayWarning:
    @property
    def move_number(self) -> int:
        """1-based."""
    @property
    def code(self) -> str: ...

@final
class Replay:
    """Every position of a replayed record and its warnings."""

    @property
    def positions(self) -> list[Position]:
        """The starting position, then the position after each move."""
    @property
    def warnings(self) -> list[ReplayWarning]: ...

def parse_sgf(data: bytes) -> Collection:
    """Parses SGF bytes in any supported encoding; raises `SgfError`."""

def extract(tree: SgfTree) -> GameRecord:
    """Reads the main line of `tree`; raises `ExtractError`."""
