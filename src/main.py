from __future__ import annotations

import os
from pathlib import Path

from src.katago_client import EngineClient, KataGoClient, KataGoUnavailableError, MockEngineClient
from src.review_service import (
    build_review_outputs_for_game,
    build_review_outputs_for_sgf,
    build_review_report_for_sgf,
    build_structured_review_for_game,
    build_structured_review_for_sgf,
    build_structured_review_for_sgf_text,
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
