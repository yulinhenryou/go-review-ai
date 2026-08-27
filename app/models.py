from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.game import MAX_MOVES, GameMove, GameRecord, validate_game


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class PlayerNamesPayload(InputModel):
    black: str | None = Field(None, max_length=256)
    white: str | None = Field(None, max_length=256)


class MovePayload(InputModel):
    color: Literal["B", "W"]
    sgf: str | None = Field(..., max_length=2)


class GamePayload(InputModel):
    board_size: int
    rules: Literal["japanese", "chinese"] | None = None
    komi: float | None = None
    players: PlayerNamesPayload | None = None
    result: str | None = Field(None, max_length=256)
    moves: list[MovePayload] = Field(..., min_length=1, max_length=MAX_MOVES)

    def to_game_record(self, *, require_metadata: bool = True) -> GameRecord:
        game = GameRecord(
            board_size=self.board_size, rules=self.rules, komi=self.komi,
            black_player=self.players.black if self.players else None,
            white_player=self.players.white if self.players else None,
            result=self.result,
            moves=tuple(GameMove(color=move.color, point=move.sgf) for move in self.moves),
        )
        validate_game(game, require_metadata=require_metadata)
        return game

    def to_parsed_game(self) -> GameRecord:
        return self.to_game_record()


class AnalyzeMovesPayload(GamePayload):
    loss_threshold: float = Field(1.0, ge=0.0, le=361.0)
    limit: int = Field(3, ge=1, le=MAX_MOVES)
