from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.sgf_parser import ParsedGame, ParsedMove


class PlayerNamesPayload(BaseModel):
    black: str | None = None
    white: str | None = None


class MovePayload(BaseModel):
    color: Literal["B", "W"]
    sgf: str | None = None


class AnalyzeMovesPayload(BaseModel):
    board_size: int = Field(..., gt=0)
    komi: float | None = None
    players: PlayerNamesPayload | None = None
    moves: list[MovePayload]
    loss_threshold: float = Field(1.0, ge=0.0)
    limit: int = Field(3, gt=0)

    def to_parsed_game(self) -> ParsedGame:
        parsed_moves: list[ParsedMove] = []

        for move in self.moves:
            _validate_move_coordinate(move.sgf, self.board_size)
            parsed_moves.append(ParsedMove(color=move.color, point=move.sgf))

        return ParsedGame(
            board_size=self.board_size,
            komi=self.komi,
            black_player=self.players.black if self.players else None,
            white_player=self.players.white if self.players else None,
            result=None,
            moves=parsed_moves,
        )


def _validate_move_coordinate(move: str | None, board_size: int) -> None:
    if move is None:
        return
    if len(move) != 2 or not move.isalpha() or not move.islower():
        raise ValueError("Each move.sgf must be a lowercase 2-letter SGF coordinate or null")

    x = ord(move[0]) - ord("a")
    y = ord(move[1]) - ord("a")
    if x < 0 or y < 0 or x >= board_size or y >= board_size:
        raise ValueError(f"Move out of board range for board_size={board_size}: {move}")
