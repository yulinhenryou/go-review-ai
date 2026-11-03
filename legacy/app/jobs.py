"""Single-instance, bounded, ephemeral jobs. Only the worker owns its engine."""
from collections import deque
from dataclasses import dataclass, field
import json
import secrets
import threading
import time

from src.analysis_control import AnalysisCancelled, AnalysisControl, AnalysisTimedOut
from src.engine_types import KataGoUnavailableError
from src.game import GameRecord, input_preview, validate_game, validate_review_options
from src.review_service import build_structured_review_for_game

TERMINAL = {"succeeded", "failed", "cancelled"}


class JobError(RuntimeError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.status = code, status


@dataclass
class Job:
    id: str
    game: GameRecord | None
    options: tuple
    control: AnalysisControl
    state: str = "queued"
    completed: int = 0
    total: int = 0
    result_json: str | None = None
    error: dict | None = None
    finished: float | None = None
    created: float = field(default_factory=time.monotonic)


class JobManager:
    def __init__(self, engine_factory, *, queue_capacity=2, timeout=900, retention=1800,
                 max_results=16, max_result_bytes=8 * 1024 * 1024, max_store_bytes=32 * 1024 * 1024):
        if not 0 <= queue_capacity <= 8 or not 0 < timeout <= 3600 or not 0 < retention <= 86400:
            raise ValueError("Invalid job capacity or time limits")
        if not 1 <= max_results <= 64 or min(max_result_bytes, max_store_bytes) <= 0:
            raise ValueError("Invalid result limits")
        self.engine_factory = engine_factory
        self.capacity, self.timeout, self.retention = queue_capacity + 1, timeout, retention
        self.max_results, self.max_result_bytes, self.max_store_bytes = max_results, max_result_bytes, max_store_bytes
        self._jobs, self._queue = {}, deque()
        self._condition = threading.Condition(threading.RLock())
        self._thread = None
        self._closed = False

    def submit(self, game, options=(3.0, 5, 5.0)):
        if game is not None:
            validate_game(game)
            validate_review_options(*options)
        with self._condition:
            self._purge()
            if self._closed:
                raise JobError("service_stopping", "Service is stopping", 503)
            if sum(job.state not in TERMINAL for job in self._jobs.values()) >= self.capacity:
                raise JobError("queue_full", "Analysis queue is full; try again later", 429)
            job_id = secrets.token_urlsafe(24)
            control = AnalysisControl(timeout=self.timeout, progress=lambda done, total: self._progress(job_id, done, total))
            job = Job(job_id, game, tuple(options), control, total=len(game.moves) + 1 if game else 0)
            self._jobs[job_id] = job
            self._queue.append(job_id)
            if self._thread is None:
                self._thread = threading.Thread(target=self._work, name="go-review-worker", daemon=True)
                self._thread.start()
            self._condition.notify_all()
            return self._view(job)

    def get(self, job_id):
        with self._condition:
            self._purge()
            return self._view(self._find(job_id))

    def input(self, job_id):
        with self._condition:
            self._purge()
            game = self._find(job_id).game
        if game is None:
            raise JobError("job_unavailable", "Job unavailable or expired; submit again", 404)
        return replay_preview(game)

    def cancel(self, job_id):
        with self._condition:
            self._purge()
            job = self._find(job_id)
            if job.state not in TERMINAL:
                job.control.cancelled.set()
                if job.state == "queued":
                    self._queue.remove(job_id)
                    self._finish(job, "cancelled")
            self._condition.notify_all()
            return self._view(job)

    def execute(self, game, options=(3.0, 5, 5.0)):
        """Compatibility endpoints use the same capacity/worker, never bypass it."""
        job_id = self.submit(game, options)["id"]
        with self._condition:
            job = self._find(job_id)
            while job.state not in TERMINAL:
                self._condition.wait(.25)
            value = self._view(job)
            self._jobs.pop(job_id, None)
            self._condition.notify_all()
        if value["state"] == "succeeded":
            return value["result"]
        error = value["error"] or {"code": "analysis_cancelled", "message": "Analysis cancelled"}
        raise JobError(error["code"], error["message"], 504 if error["code"] == "analysis_timeout" else 503)

    def close(self):
        with self._condition:
            self._closed = True
            for job in self._jobs.values():
                job.control.cancelled.set()
                if job.state == "queued":
                    self._finish(job, "cancelled")
            self._queue.clear()
            thread = self._thread
            self._condition.notify_all()
        if thread:
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("Analysis worker did not stop")
        with self._condition:
            self._jobs.clear()

    def _find(self, job_id):
        if job_id not in self._jobs:
            raise JobError("job_unavailable", "Job unavailable or expired; submit again", 404)
        return self._jobs[job_id]

    def _view(self, job):
        return {"schema_version": "1.0", "id": job.id, "state": job.state,
                "cancel_requested": job.control.cancelled.is_set() and job.state not in TERMINAL,
                "progress": {"completed": job.completed, "total": job.total},
                "queue_position": list(self._queue).index(job.id) + 1 if job.id in self._queue else 0,
                "retention_seconds": self.retention,
                "result": json.loads(job.result_json) if job.result_json is not None else None,
                "error": dict(job.error) if job.error else None}

    def _progress(self, job_id, completed, total):
        with self._condition:
            job = self._find(job_id)
            if total != job.total or not job.completed <= completed <= total:
                raise RuntimeError("Invalid engine progress")
            job.completed = completed

    def _finish(self, job, state, error=None):
        job.state, job.error, job.finished = state, error, time.monotonic()
        self._condition.notify_all()

    def _purge(self):
        terminal = sorted((j for j in self._jobs.values() if j.finished is not None), key=lambda j: j.finished)
        size = sum(len(j.result_json.encode()) for j in terminal if j.result_json)
        count = len(terminal)
        for job in terminal:
            if time.monotonic() - job.finished < self.retention and count <= self.max_results and size <= self.max_store_bytes:
                break
            self._jobs.pop(job.id, None)
            size -= len(job.result_json.encode()) if job.result_json else 0
            count -= 1

    def _work(self):
        while True:
            with self._condition:
                self._purge()
                if self._closed or not self._jobs:
                    self._thread = None
                    return
                if not self._queue:
                    self._condition.wait(.5)
                    continue
                job = self._find(self._queue.popleft())
                job.state = "running"
            try:
                job.control.checkpoint()
                engine = self.engine_factory()
                configure = getattr(engine, "configure_control", None)
                if configure:
                    configure(job.control)
                job.control.checkpoint()
                if job.game is None:
                    if not hasattr(engine, "readiness"):
                        raise KataGoUnavailableError("Real engine readiness is unavailable")
                    result = engine.readiness()
                else:
                    result = build_structured_review_for_game(
                        job.game, engine, loss_threshold=job.options[0], limit=job.options[1],
                        severe_threshold=job.options[2]).to_dict()
                job.control.checkpoint()
                encoded = json.dumps(result, ensure_ascii=True, allow_nan=False)
                if len(encoded.encode()) > self.max_result_bytes:
                    raise RuntimeError("Result exceeds configured storage budget")
                with self._condition:
                    job.control.checkpoint()
                    job.completed = job.total
                    job.result_json = encoded
                    self._finish(job, "succeeded")
            except AnalysisCancelled:
                with self._condition:
                    self._finish(job, "cancelled")
            except Exception as exc:
                code = "analysis_timeout" if isinstance(exc, AnalysisTimedOut) else (
                    "engine_unavailable" if isinstance(exc, KataGoUnavailableError) else "analysis_failed")
                messages = {"analysis_timeout": "Analysis timed out; submit a shorter record",
                            "engine_unavailable": "Real KataGo is unavailable; no simulated report was generated",
                            "analysis_failed": "Analysis failed; no complete report was generated"}
                with self._condition:
                    self._finish(job, "cancelled" if job.control.cancelled.is_set() else "failed",
                                 None if job.control.cancelled.is_set() else {"code": code, "message": messages[code]})


def replay_preview(game):
    positions = validate_game(game, require_metadata=False)
    preview = input_preview(game)
    numbered, history = [], {}
    for index, position in enumerate(positions):
        if index and game.moves[index - 1].point is not None:
            history[game.moves[index - 1].point] = index
        numbered.append({"next_player": position.next_player, "stones": [
            {"color": color, "sgf": point, "move_number": history[point]} for color, point in position.stones]})
    return {**preview, "positions": numbered}
