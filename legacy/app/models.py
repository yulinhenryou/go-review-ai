from __future__ import annotations

from typing import Literal
from dataclasses import replace

from pydantic import BaseModel, ConfigDict, Field

from src.game import MAX_MOVES, GameMove, GameRecord, validate_game
from src.mistake_severity import DEFAULT_LOSS_THRESHOLD, DEFAULT_SEVERE_THRESHOLD, MAX_REVIEW_MISTAKES


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
    loss_threshold: float = Field(DEFAULT_LOSS_THRESHOLD, ge=0.0, le=361.0)
    severe_threshold: float = Field(DEFAULT_SEVERE_THRESHOLD, ge=0.0, le=361.0)
    limit: int = Field(MAX_REVIEW_MISTAKES, ge=1, le=MAX_REVIEW_MISTAKES)


class JobPayload(AnalyzeMovesPayload):
    input_warnings: list[Literal["first_variation_only"]] = Field(default_factory=list, max_length=1)

    def to_game_record(self, *, require_metadata: bool = True) -> GameRecord:
        return replace(super().to_game_record(require_metadata=require_metadata), warnings=tuple(self.input_warnings))
