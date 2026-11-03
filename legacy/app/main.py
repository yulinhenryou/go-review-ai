from __future__ import annotations

from typing import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.limits import BodyLimitMiddleware, NoStoreMiddleware
from app.models import AnalyzeMovesPayload, GamePayload, JobPayload
from app.jobs import JobError, JobManager, replay_preview
from app.settings import allowed_origins, job_options
from src.game import (
    MAX_SGF_BYTES, GameInputError, GameRecord,
    validate_game, validate_review_options,
)
from src.katago_client import EngineClient
from src.engine_factory import build_default_engine
from src.engine_types import KataGoUnavailableError
from src.mistake_severity import DEFAULT_LOSS_THRESHOLD, DEFAULT_SEVERE_THRESHOLD, MAX_REVIEW_MISTAKES
from src.sgf_parser import parse_sgf_bytes

EngineFactory = Callable[[], EngineClient]


def create_app(
    engine_factory: EngineFactory | None = None,
    *,
    job_manager: JobManager | None = None,
    public: bool = False,
) -> FastAPI:
    selected_engine_factory = engine_factory or build_default_engine
    jobs = job_manager or JobManager(selected_engine_factory, **job_options())

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            await run_in_threadpool(jobs.close)

    hidden_docs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if public else {}
    app = FastAPI(title="go-review-ai API", version="0.5.0", lifespan=lifespan, **hidden_docs)
    app.state.jobs = jobs
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(NoStoreMiddleware)

    @app.exception_handler(JobError)
    async def job_error(_request, exc: JobError):
        return JSONResponse({"detail": str(exc), "error": {"code": exc.code, "message": str(exc)}},
                            status_code=exc.status, headers={"Retry-After": "2"} if exc.status == 429 else None)

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
    async def analysis_error(_request, exc: RuntimeError) -> JSONResponse:
        code = "analysis_failed"
        message = "Analysis failed; check the server's engine configuration"
        if isinstance(exc, KataGoUnavailableError):
            code, message = "engine_unavailable", "Real KataGo is unavailable; no simulated report was generated"
        return JSONResponse(
            {"detail": message, "error": {"code": code, "message": message,
             "field": None, "move_number": None}}, status_code=503,
        )

    async def uploaded_game(file: UploadFile, rules: str | None, komi: float | None) -> GameRecord:
        try:
            data = await file.read(MAX_SGF_BYTES + 1)
        finally:
            await file.close()
        return parse_sgf_bytes(data, rules=rules, komi=komi)

    def review(game: GameRecord, loss_threshold: float, limit: int, severe_threshold: float) -> dict[str, object]:
        validate_game(game)
        validate_review_options(loss_threshold, limit, severe_threshold)
        return jobs.execute(game, (loss_threshold, limit, severe_threshold))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict:
        return jobs.execute(None)

    @app.post("/api/v1/parse-sgf")
    async def parse_upload(
        file: UploadFile = File(...), rules: str | None = None, komi: float | None = None,
    ) -> dict[str, object]:
        return replay_preview(await uploaded_game(file, rules, komi))

    @app.post("/api/v1/validate-moves")
    def validate_moves(payload: GamePayload) -> dict[str, object]:
        return replay_preview(payload.to_game_record(require_metadata=False))

    @app.post("/api/v1/replay-moves")
    def replay_moves(payload: GamePayload):
        return replay_preview(payload.to_game_record(require_metadata=False))

    @app.post("/api/v1/jobs", status_code=202)
    def submit_job(payload: JobPayload):
        return jobs.submit(payload.to_game_record(), (payload.loss_threshold, payload.limit, payload.severe_threshold))

    @app.get("/api/v1/jobs/{job_id}")
    def job_status(job_id: str):
        return jobs.get(job_id)

    @app.get("/api/v1/jobs/{job_id}/input")
    def job_input(job_id: str):
        return jobs.input(job_id)

    @app.delete("/api/v1/jobs/{job_id}")
    def cancel_job(job_id: str):
        return jobs.cancel(job_id)

    @app.post("/api/v1/analyze-sgf")
    async def analyze_sgf(
        file: UploadFile = File(...),
        rules: str | None = None,
        komi: float | None = None,
        loss_threshold: float = DEFAULT_LOSS_THRESHOLD,
        limit: int = MAX_REVIEW_MISTAKES,
        severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
    ) -> dict[str, object]:
        game = await uploaded_game(file, rules, komi)
        return await run_in_threadpool(review, game, loss_threshold, limit, severe_threshold)

    @app.post("/api/v1/analyze-moves")
    def analyze_moves(payload: AnalyzeMovesPayload) -> dict[str, object]:
        return review(payload.to_game_record(), payload.loss_threshold, payload.limit, payload.severe_threshold)

    return app


app = create_app()
