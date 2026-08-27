from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.katago_client import EngineClient, PositionAnalysis, PositionInput
from src.game import validate_game
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


@dataclass(frozen=True)
class GameAnalysis:
    move_results: list[MoveAnalysisResult]
    current_position: PositionAnalysis
    current_position_input: PositionInput


def analyze_game(game: ParsedGame, engine: EngineClient) -> list[MoveAnalysisResult]:
    """Analyze each main-line move with a position-like input built before the move."""
    validate_game(game)
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
            rules=game.rules,
            analysis_kind="played_move",
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


def analyze_game_state(game: ParsedGame, engine: EngineClient) -> GameAnalysis:
    results = analyze_game(game, engine)
    current_position_input = PositionInput(
        board_size=game.board_size,
        komi=game.komi,
        to_play=_next_player(game.moves),
        moves=tuple((move.color, move.point) for move in game.moves),
        played_move=None,
        rules=game.rules,
        analysis_kind="current_position",
    )
    current_position = engine.analyze_position(current_position_input)
    return GameAnalysis(
        move_results=results,
        current_position=current_position,
        current_position_input=current_position_input,
    )


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


def _next_player(moves: list[object]) -> str:
    return "B" if len(moves) % 2 == 0 else "W"
