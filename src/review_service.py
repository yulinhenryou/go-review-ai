from __future__ import annotations

from pathlib import Path

from src.analyzer import analyze_game_state
from src.classifier import classify_all_results, classify_selected_mistakes
from src.game import validate_game, validate_review_options
from src.katago_client import EngineClient
from src.mistake_selector import select_mistakes_above_threshold
from src.report_writer import generate_review_report
from src.review_result import ReviewResult, build_review_result
from src.sgf_parser import ParsedGame, parse_sgf, parse_sgf_file


def build_review_outputs_for_sgf(
    sgf_path: str | Path,
    engine: EngineClient,
    loss_threshold: float = 1.0,
    limit: int = 3,
) -> tuple[str, ReviewResult]:
    game = parse_sgf_file(sgf_path)
    return build_review_outputs_for_game(
        game=game,
        engine=engine,
        loss_threshold=loss_threshold,
        limit=limit,
    )


def build_review_outputs_for_game(
    game: ParsedGame,
    engine: EngineClient,
    loss_threshold: float = 1.0,
    limit: int = 3,
) -> tuple[str, ReviewResult]:
    validate_game(game)
    validate_review_options(loss_threshold, limit)
    analysis = analyze_game_state(game, engine)
    results = analysis.move_results
    threshold_mistakes = select_mistakes_above_threshold(
        results,
        loss_threshold=loss_threshold,
    )
    selected = threshold_mistakes[:limit]
    classified = classify_selected_mistakes(selected, results)
    classified_threshold = classify_selected_mistakes(threshold_mistakes, results)
    all_classified = classify_all_results(results)
    review_result = build_review_result(
        game=game,
        selected_mistakes=classified,
        threshold_mistakes=classified_threshold,
        all_classified=all_classified,
        results=results,
        current_position_analysis=analysis.current_position,
        next_player=analysis.current_position_input.to_play,
        loss_threshold=loss_threshold,
    )
    return (
        generate_review_report(game, classified, review=review_result),
        review_result,
    )


def build_review_report_for_sgf(
    sgf_path: str | Path,
    engine: EngineClient,
    loss_threshold: float = 1.0,
    limit: int = 3,
) -> str:
    report, _review_result = build_review_outputs_for_sgf(
        sgf_path=sgf_path,
        engine=engine,
        loss_threshold=loss_threshold,
        limit=limit,
    )
    return report


def build_structured_review_for_sgf(
    sgf_path: str | Path,
    engine: EngineClient,
    loss_threshold: float = 1.0,
    limit: int = 3,
) -> ReviewResult:
    _report, review_result = build_review_outputs_for_sgf(
        sgf_path=sgf_path,
        engine=engine,
        loss_threshold=loss_threshold,
        limit=limit,
    )
    return review_result


def build_structured_review_for_game(
    game: ParsedGame,
    engine: EngineClient,
    loss_threshold: float = 1.0,
    limit: int = 3,
) -> ReviewResult:
    _report, review_result = build_review_outputs_for_game(
        game=game,
        engine=engine,
        loss_threshold=loss_threshold,
        limit=limit,
    )
    return review_result


def build_structured_review_for_sgf_text(
    sgf_text: str,
    engine: EngineClient,
    loss_threshold: float = 1.0,
    limit: int = 3,
) -> ReviewResult:
    game = parse_sgf(sgf_text)
    return build_structured_review_for_game(
        game=game,
        engine=engine,
        loss_threshold=loss_threshold,
        limit=limit,
    )
