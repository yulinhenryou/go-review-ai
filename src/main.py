from __future__ import annotations

from pathlib import Path

from src.katago_client import EngineClient
from src.engine_factory import build_default_engine
from src.review_service import (
    build_review_outputs_for_game,
    build_review_outputs_for_sgf,
    build_review_report_for_sgf,
    build_structured_review_for_game,
    build_structured_review_for_sgf,
    build_structured_review_for_sgf_text,
)


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
