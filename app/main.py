from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, File, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.limits import BodyLimitMiddleware
from app.models import AnalyzeMovesPayload, GamePayload
from src.game import (
    MAX_SGF_BYTES, GameInputError, GameRecord, input_preview,
    validate_game, validate_review_options,
)
from src.katago_client import EngineClient
from src.main import build_default_engine
from src.review_service import build_structured_review_for_game
from src.sgf_parser import parse_sgf_bytes

EngineFactory = Callable[[], EngineClient]


def create_app(engine_factory: EngineFactory | None = None) -> FastAPI:
    selected_engine_factory = engine_factory or build_default_engine
    app = FastAPI(title="go-review-ai API", version="0.2.0")
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(GameInputError)
    async def input_error(_request, exc: GameInputError) -> JSONResponse:
        return JSONResponse(
            {"detail": str(exc), "error": {
                "code": exc.code, "message": str(exc), "field": exc.field,
                "move_number": exc.move_number,
            }},
            status_code=413 if exc.code == "input_too_large" else 400,
        )

    @app.exception_handler(RequestValidationError)
    async def request_error(_request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo raw input or nonfinite values from Pydantic's error context.
        issues = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
        message = "Invalid request fields"
        return JSONResponse(
            {"detail": message, "error": {
                "code": "invalid_request", "message": message, "field": None,
                "move_number": None, "issues": issues,
            }}, status_code=422,
        )

    @app.exception_handler(RuntimeError)
    async def analysis_error(_request, _exc: RuntimeError) -> JSONResponse:
        message = "Analysis failed; check the server's engine configuration"
        return JSONResponse(
            {"detail": message, "error": {"code": "analysis_failed", "message": message,
             "field": None, "move_number": None}}, status_code=503,
        )

    async def uploaded_game(file: UploadFile, rules: str | None, komi: float | None) -> GameRecord:
        try:
            data = await file.read(MAX_SGF_BYTES + 1)
        finally:
            await file.close()
        return parse_sgf_bytes(data, rules=rules, komi=komi)

    def review(game: GameRecord, loss_threshold: float, limit: int) -> dict[str, object]:
        validate_game(game)
        validate_review_options(loss_threshold, limit)
        result = build_structured_review_for_game(
            game, engine=selected_engine_factory(), loss_threshold=loss_threshold, limit=limit,
        )
        return result.to_dict()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/parse-sgf")
    async def parse_upload(
        file: UploadFile = File(...), rules: str | None = None, komi: float | None = None,
    ) -> dict[str, object]:
        return input_preview(await uploaded_game(file, rules, komi))

    @app.post("/api/v1/validate-moves")
    def validate_moves(payload: GamePayload) -> dict[str, object]:
        return input_preview(payload.to_game_record(require_metadata=False))

    @app.post("/api/v1/analyze-sgf")
    async def analyze_sgf(
        file: UploadFile = File(...),
        rules: str | None = None,
        komi: float | None = None,
        loss_threshold: float = 1.0,
        limit: int = 3,
    ) -> dict[str, object]:
        game = await uploaded_game(file, rules, komi)
        return review(game, loss_threshold, limit)

    @app.post("/api/v1/analyze-moves")
    def analyze_moves(payload: AnalyzeMovesPayload) -> dict[str, object]:
        return review(payload.to_game_record(), payload.loss_threshold, payload.limit)

    return app


app = create_app()
