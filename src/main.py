from __future__ import annotations

from pathlib import Path

from src.analyzer import analyze_sgf_file
from src.classifier import classify_selected_mistakes
from src.katago_client import EngineClient, MockEngineClient
from src.mistake_selector import select_top_mistakes
from src.report_writer import generate_review_report
from src.sgf_parser import parse_sgf_file


def build_review_report_for_sgf(
    sgf_path: str | Path,
    engine: EngineClient,
    loss_threshold: float = 1.0,
    limit: int = 3,
) -> str:
    game = parse_sgf_file(sgf_path)
    results = analyze_sgf_file(sgf_path, engine)
    selected = select_top_mistakes(results, loss_threshold=loss_threshold, limit=limit)
    classified = classify_selected_mistakes(selected, results)
    return generate_review_report(game, classified)


def print_sample_report(sgf_path: str | Path = "samples/sample_game.sgf") -> None:
    report = build_review_report_for_sgf(
        sgf_path=sgf_path,
        engine=MockEngineClient(candidate_count=3),
        loss_threshold=1.0,
        limit=3,
    )
    print(report)


if __name__ == "__main__":
    print_sample_report()
