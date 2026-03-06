from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.models import AnalyzeMovesPayload
from src.katago_client import EngineClient
from src.main import (
    build_default_engine,
    build_structured_review_for_game,
    build_structured_review_for_sgf_text,
)


EngineFactory = Callable[[], EngineClient]


def create_app(engine_factory: EngineFactory | None = None) -> FastAPI:
    selected_engine_factory = engine_factory or build_default_engine
    app = FastAPI(title="go-review-ai API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/analyze-sgf")
    async def analyze_sgf(
        file: UploadFile = File(...),
        loss_threshold: float = 1.0,
        limit: int = 3,
    ) -> dict[str, object]:
        if limit <= 0:
            raise HTTPException(status_code=400, detail="limit must be positive")

        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        try:
            sgf_text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="SGF file must be UTF-8 text") from exc

        try:
            review = build_structured_review_for_sgf_text(
                sgf_text=sgf_text,
                engine=selected_engine_factory(),
                loss_threshold=loss_threshold,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return review.to_dict()

    @app.post("/api/v1/analyze-moves")
    def analyze_moves(payload: AnalyzeMovesPayload) -> dict[str, object]:
        try:
            game = payload.to_parsed_game()
            review = build_structured_review_for_game(
                game=game,
                engine=selected_engine_factory(),
                loss_threshold=payload.loss_threshold,
                limit=payload.limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return review.to_dict()

    return app


app = create_app()
