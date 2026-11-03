from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

Color = Literal["B", "W"]
Move = str


class KataGoUnavailableError(RuntimeError):
    """The configured real engine cannot be started or used."""


class EngineProtocolError(RuntimeError):
    """Engine output is invalid or cannot be matched to a request."""


@dataclass(frozen=True)
class PositionInput:
    board_size: int
    komi: float | None
    to_play: Color
    moves: tuple[tuple[Color, Move | None], ...]
    played_move: Move | None
    rules: Literal["japanese", "chinese"] = "japanese"
    analysis_kind: Literal["played_move", "current_position"] = "played_move"


@dataclass(frozen=True)
class PVMove:
    color: Color
    move: str


@dataclass(frozen=True)
class CandidateMove:
    move: Move
    score_estimate: float | None
    winrate: float | None
    pv: tuple[PVMove, ...] = ()
    visits: int | None = None
    score_black: float | None = None
    winrate_black: float | None = None


@dataclass(frozen=True)
class AnalysisEvidence:
    engine_version: str
    model_sha256: str
    model_id: str
    rules: str
    komi: float
    max_visits: int
    request_id: str
    turn_number: int
    root_visits: int | None
    elapsed_seconds: float
    played_source: str
    played_request_id: str | None
    config_sha256: str = ""
    warnings: tuple[str, ...] = ()
    raw_perspective: str = "BLACK"
    value_perspective: str = "side_to_move"
    score_unit: str = "points"


@dataclass(frozen=True)
class PositionAnalysis:
    best_move: Move | None
    played_move: Move | None
    estimated_loss: float | None
    score_estimate: float | None
    winrate: float | None
    played_score_estimate: float | None
    played_winrate: float | None
    top_candidates: tuple[CandidateMove, ...]
    pv_summary: str
    raw_score_loss: float | None = None
    score_black: float | None = None
    winrate_black: float | None = None
    played_score_black: float | None = None
    played_winrate_black: float | None = None
    played_candidate: CandidateMove | None = None
    evidence: AnalysisEvidence | None = None


class EngineClient(Protocol):
    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        """Analyze one position. Missing evidence remains None."""
