from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.katago_client import EngineClient, PositionAnalysis, PositionInput
from src.sgf_parser import ParsedGame, parse_sgf_file


@dataclass(frozen=True)
class MoveAnalysisResult:
    move_number: int
    color: str
    played_move: str | None
    recommended_move: str
    estimated_loss: float
    position_input: PositionInput
    engine_analysis: PositionAnalysis


def analyze_game(game: ParsedGame, engine: EngineClient) -> list[MoveAnalysisResult]:
    """Analyze each main-line move with a position-like input built before the move."""
    history: list[tuple[str, str | None]] = []
    results: list[MoveAnalysisResult] = []

    for move_number, parsed_move in enumerate(game.moves, start=1):
        if parsed_move.color not in {"B", "W"}:
            raise ValueError(f"Unsupported move color: {parsed_move.color}")

        position = PositionInput(
            board_size=game.board_size,
            komi=game.komi,
            to_play=parsed_move.color,
            moves=tuple(history),
            played_move=parsed_move.point,
        )

        analysis = engine.analyze_position(position)
        results.append(
            MoveAnalysisResult(
                move_number=move_number,
                color=parsed_move.color,
                played_move=parsed_move.point,
                recommended_move=analysis.best_move,
                estimated_loss=analysis.estimated_loss,
                position_input=position,
                engine_analysis=analysis,
            )
        )

        history.append((parsed_move.color, parsed_move.point))

    return results


def analyze_sgf_file(path: str | Path, engine: EngineClient) -> list[MoveAnalysisResult]:
    game = parse_sgf_file(path)
    return analyze_game(game, engine)


def print_move_summaries(results: list[MoveAnalysisResult]) -> None:
    for result in results:
        played = result.played_move if result.played_move is not None else "pass"
        print(
            f"Move {result.move_number}: "
            f"played={played} recommended={result.recommended_move} "
            f"loss={result.estimated_loss:.2f}"
        )
