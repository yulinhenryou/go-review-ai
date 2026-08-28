from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from sgfmill.boards import Board

Color = Literal["B", "W"]
Rules = Literal["japanese", "chinese"]
MAX_SGF_BYTES = 1024 * 1024
MAX_MOVES = 500
MAX_SGF_NODES = 5000


class GameInputError(ValueError):
    def __init__(
        self, code: str, message: str, *, field: str | None = None,
        move_number: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.move_number = move_number


@dataclass(frozen=True)
class GameMove:
    color: Color
    point: str | None


@dataclass(frozen=True)
class GameRecord:
    board_size: int
    komi: float | None
    black_player: str | None
    white_player: str | None
    result: str | None
    moves: tuple[GameMove, ...]
    rules: Rules | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "moves", tuple(self.moves))
        object.__setattr__(self, "warnings", tuple(self.warnings))

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(name for name in ("rules", "komi") if getattr(self, name) is None)

    @property
    def record_status(self) -> str:
        # A stored result is metadata, not proof that every move was recorded.
        return "result_recorded" if self.result and self.result != "?" else "unfinished_or_unknown"

    def to_dict(self) -> dict[str, object]:
        return {
            "board_size": self.board_size, "rules": self.rules, "komi": self.komi,
            "players": {"black": self.black_player, "white": self.white_player},
            "result": self.result, "record_status": self.record_status,
            "moves": [{"color": move.color, "sgf": move.point} for move in self.moves],
        }


@dataclass(frozen=True)
class BoardSnapshot:
    stones: tuple[tuple[str, str], ...]
    next_player: Color


def normalize_rules(value: str | None) -> Rules | None:
    if value is None:
        return None
    if not isinstance(value, str) or value.strip().lower() not in {"japanese", "chinese"}:
        raise GameInputError("unsupported_rules", "Rules must be Japanese or Chinese", field="rules")
    return value.strip().lower()  # type: ignore[return-value]


def validate_komi(value: float | None) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or not -150 <= value <= 150
        or value * 2 != int(value * 2)
    ):
        raise GameInputError(
            "invalid_komi", "Komi must be a finite half-point increment from -150 to 150", field="komi"
        )


def validate_review_options(loss_threshold: float, limit: int, severe_threshold: float = 5.0) -> None:
    if (
        isinstance(loss_threshold, bool) or not isinstance(loss_threshold, (int, float))
        or not math.isfinite(loss_threshold) or not 0 <= loss_threshold <= 361
    ):
        raise GameInputError("invalid_threshold", "loss_threshold must be finite and between 0 and 361", field="loss_threshold")
    if (
        isinstance(severe_threshold, bool) or not isinstance(severe_threshold, (int, float))
        or not math.isfinite(severe_threshold) or not loss_threshold <= severe_threshold <= 361
    ):
        raise GameInputError("invalid_threshold", "severe_threshold must be finite, >= loss_threshold and <= 361", field="severe_threshold")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise GameInputError("invalid_limit", "limit must be an integer between 1 and 5", field="limit")


def validate_game(game: GameRecord, *, require_metadata: bool = True) -> tuple[BoardSnapshot, ...]:
    if type(game.board_size) is not int or game.board_size != 19:
        raise GameInputError("unsupported_board_size", "Only SZ[19] / board_size 19 is supported", field="board_size")
    if game.rules is not None and game.rules not in {"japanese", "chinese"}:
        raise GameInputError("unsupported_rules", "Rules must be japanese or chinese", field="rules")
    validate_komi(game.komi)
    for field in ("black_player", "white_player", "result"):
        value = getattr(game, field)
        if value is not None and (not isinstance(value, str) or len(value) > 256):
            raise GameInputError("invalid_metadata", f"{field} must be text of at most 256 characters", field=field)
    if not 1 <= len(game.moves) <= MAX_MOVES:
        raise GameInputError("invalid_move_count", "A game must contain 1-500 moves", field="moves")

    board = Board(game.board_size)
    snapshots = [BoardSnapshot((), "B")]
    ko_point = None
    consecutive_passes = 0
    for number, move in enumerate(game.moves, start=1):
        def fail(code: str, message: str) -> None:
            raise GameInputError(code, f"Move {number}: {message}", field="moves", move_number=number)

        if not isinstance(move, GameMove):
            fail("invalid_move", "expected a GameMove")
        expected = "B" if number % 2 else "W"
        if move.color != expected:
            fail("invalid_turn", f"expected {expected} to play")
        if consecutive_passes == 2:
            fail("unsupported_resumption", "play after two consecutive passes is not supported in v1")
        if move.point is None:
            consecutive_passes += 1
            ko_point = None
        else:
            point = move.point
            if not isinstance(point, str) or len(point) != 2 or any(c < "a" or c > "s" for c in point):
                fail("invalid_coordinate", "SGF coordinates must contain two letters a-s; use null for pass")
            row, col = game.board_size - 1 - (ord(point[1]) - 97), ord(point[0]) - 97
            if board.get(row, col) is not None:
                fail("occupied_point", f"point {point} is occupied")
            if (row, col) == ko_point:
                fail("ko_violation", "immediate ko recapture is forbidden")
            # sgfmill owns group/capture logic; it reports ko but permits suicide.
            ko_point = board.play(row, col, move.color.lower())
            if board.get(row, col) is None:
                fail("suicide", "self-capture is forbidden under the selected rules")
            consecutive_passes = 0
        stones = tuple(sorted(
            (color.upper(), chr(col + 97) + chr(game.board_size - 1 - row + 97))
            for color, (row, col) in board.list_occupied_points()
        ))
        snapshots.append(BoardSnapshot(stones, "W" if expected == "B" else "B"))

    if require_metadata and game.missing_fields:
        raise GameInputError(
            "missing_metadata", "Confirm missing metadata: " + ", ".join(game.missing_fields),
            field=game.missing_fields[0],
        )
    return tuple(snapshots)


def input_preview(game: GameRecord) -> dict[str, object]:
    positions = validate_game(game, require_metadata=False)
    return {
        "schema_version": "1.0", "game": game.to_dict(),
        "status": "needs_metadata" if game.missing_fields else "ready",
        "missing_fields": list(game.missing_fields), "warnings": list(game.warnings),
        "final_position": {
            "next_player": positions[-1].next_player,
            "stones": [{"color": color, "sgf": point} for color, point in positions[-1].stones],
        },
    }
