from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PositionInput:
    board_size: int
    komi: float | None
    to_play: str
    moves: list[tuple[str, str | None]]
    played_move: str | None


@dataclass(frozen=True)
class CandidateMove:
    move: str
    score_estimate: float
    winrate: float


@dataclass(frozen=True)
class PositionAnalysis:
    best_move: str
    played_move: str | None
    estimated_loss: float
    top_candidates: list[CandidateMove]
    pv_summary: str


class EngineClient(Protocol):
    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        """Analyze one Go position and return structured results."""


class MockEngineClient:
    """Deterministic mock for pipeline development before real KataGo wiring."""

    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        _validate_position(position)

        top_candidates = _mock_candidates(position)
        best_move = top_candidates[0].move
        played_move = position.played_move

        if played_move is None:
            estimated_loss = 0.0
        elif played_move == best_move:
            estimated_loss = 0.0
        else:
            estimated_loss = round(abs(top_candidates[0].score_estimate - top_candidates[-1].score_estimate), 2)

        pv_summary = _pv_summary(position.to_play, top_candidates)

        return PositionAnalysis(
            best_move=best_move,
            played_move=played_move,
            estimated_loss=estimated_loss,
            top_candidates=top_candidates,
            pv_summary=pv_summary,
        )


def _validate_position(position: PositionInput) -> None:
    if position.to_play not in {"B", "W"}:
        raise ValueError("to_play must be 'B' or 'W'")
    if position.board_size <= 0:
        raise ValueError("board_size must be positive")


def _mock_candidates(position: PositionInput) -> list[CandidateMove]:
    opening_book = {
        "B": [
            CandidateMove(move="qd", score_estimate=1.8, winrate=0.54),
            CandidateMove(move="dp", score_estimate=1.2, winrate=0.52),
            CandidateMove(move="pq", score_estimate=0.7, winrate=0.50),
        ],
        "W": [
            CandidateMove(move="dq", score_estimate=-1.1, winrate=0.48),
            CandidateMove(move="cp", score_estimate=-1.6, winrate=0.47),
            CandidateMove(move="qq", score_estimate=-2.0, winrate=0.45),
        ],
    }

    if len(position.moves) < 2:
        return opening_book[position.to_play]

    # Slightly vary mock output by move-count bucket for deterministic diversity.
    bucket = len(position.moves) % 3
    if bucket == 0:
        return opening_book[position.to_play]
    if bucket == 1:
        return [
            CandidateMove(move="jj", score_estimate=0.9, winrate=0.53),
            CandidateMove(move="kj", score_estimate=0.3, winrate=0.50),
            CandidateMove(move="jk", score_estimate=-0.2, winrate=0.49),
        ]
    return [
        CandidateMove(move="cn", score_estimate=2.1, winrate=0.57),
        CandidateMove(move="co", score_estimate=1.3, winrate=0.54),
        CandidateMove(move="bn", score_estimate=0.6, winrate=0.51),
    ]


def _pv_summary(to_play: str, candidates: list[CandidateMove]) -> str:
    best = candidates[0].move
    reply = candidates[1].move
    if to_play == "B":
        return f"B {best} -> W {reply} -> B {candidates[2].move}"
    return f"W {best} -> B {reply} -> W {candidates[2].move}"
