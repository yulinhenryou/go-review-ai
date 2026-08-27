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
    recommended_move: str | None
    estimated_loss: float | None
    position_input: PositionInput
    engine_analysis: PositionAnalysis


@dataclass(frozen=True)
class GameAnalysis:
    move_results: list[MoveAnalysisResult]
    current_position: PositionAnalysis
    current_position_input: PositionInput


def analyze_game(game: ParsedGame, engine: EngineClient) -> list[MoveAnalysisResult]:
    """Analyze each main-line move with a position-like input built before the move."""
    positions = _positions(game)
    return _move_results(positions, _evaluate(engine, positions))


def analyze_game_state(game: ParsedGame, engine: EngineClient) -> GameAnalysis:
    positions = _positions(game)
    current_position_input = PositionInput(
        board_size=game.board_size,
        komi=game.komi,
        to_play=_next_player(game.moves),
        moves=tuple((move.color, move.point) for move in game.moves),
        played_move=None,
        rules=game.rules,
        analysis_kind="current_position",
    )
    evaluations = _evaluate(engine, positions + [current_position_input])
    return GameAnalysis(
        move_results=_move_results(positions, evaluations[:-1]),
        current_position=evaluations[-1],
        current_position_input=current_position_input,
    )


def _positions(game: ParsedGame) -> list[PositionInput]:
    validate_game(game)
    history = tuple((move.color, move.point) for move in game.moves)
    return [PositionInput(
        board_size=game.board_size, komi=game.komi, rules=game.rules,
        to_play=move.color, moves=history[:i], played_move=move.point,
    ) for i, move in enumerate(game.moves)]


def _evaluate(engine: EngineClient, positions: list[PositionInput]) -> list[PositionAnalysis]:
    batch = getattr(engine, "analyze_positions", None)
    analyses = batch(positions) if batch is not None else [engine.analyze_position(p) for p in positions]
    if len(analyses) != len(positions):
        raise RuntimeError("Engine did not return all requested positions")
    return analyses


def _move_results(positions, analyses) -> list[MoveAnalysisResult]:
    return [MoveAnalysisResult(
        move_number=i, color=position.to_play, played_move=position.played_move,
        recommended_move=analysis.best_move, estimated_loss=analysis.estimated_loss,
        position_input=position, engine_analysis=analysis,
    ) for i, (position, analysis) in enumerate(zip(positions, analyses, strict=True), 1)]


def analyze_sgf_file(path: str | Path, engine: EngineClient) -> list[MoveAnalysisResult]:
    game = parse_sgf_file(path)
    return analyze_game(game, engine)


def print_move_summaries(results: list[MoveAnalysisResult]) -> None:
    for result in results:
        played = result.played_move if result.played_move is not None else "pass"
        loss = f"{result.estimated_loss:.2f}" if result.estimated_loss is not None else "unavailable"
        print(
            f"Move {result.move_number}: "
            f"played={played} recommended={result.recommended_move} "
            f"loss={loss}"
        )


def _next_player(moves: list[object]) -> str:
    return "B" if len(moves) % 2 == 0 else "W"
