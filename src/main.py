from __future__ import annotations

import os
from pathlib import Path

from src.analyzer import analyze_game_state
from src.classifier import classify_all_results, classify_selected_mistakes
from src.katago_client import (
    EngineClient,
    KataGoClient,
    KataGoUnavailableError,
    MockEngineClient,
)
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


def build_default_engine() -> EngineClient:
    katago_path = os.environ.get("KATAGO_PATH", "katago")
    try:
        return KataGoClient.from_environment(
            katago_path=katago_path,
            candidate_count=3,
            max_visits=200,
            timeout_seconds=20.0,
        )
    except KataGoUnavailableError as exc:
        print(f"KataGo unavailable ({exc}); falling back to MockEngineClient.")
        return MockEngineClient(candidate_count=3)


def print_sample_report(
    sgf_path: str | Path = "samples/sample_game.sgf",
    engine: EngineClient | None = None,
) -> None:
    selected_engine = engine if engine is not None else build_default_engine()
    report = build_review_report_for_sgf(
        sgf_path=sgf_path,
        engine=selected_engine,
        loss_threshold=1.0,
        limit=3,
    )
    print(report)


if __name__ == "__main__":
    print_sample_report()
