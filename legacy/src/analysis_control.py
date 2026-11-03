"""Cooperative cancellation checked by the engine's owning worker."""
import threading
import time
from typing import Callable

from src.engine_types import KataGoUnavailableError


class AnalysisCancelled(RuntimeError):
    pass


class AnalysisTimedOut(KataGoUnavailableError):
    pass


class AnalysisControl:
    def __init__(self, *, timeout: float = 900, progress: Callable[[int, int], None] | None = None):
        self.cancelled = threading.Event()
        self.deadline = time.monotonic() + timeout
        self.progress = progress or (lambda completed, total: None)

    def checkpoint(self):
        if self.cancelled.is_set():
            raise AnalysisCancelled("Analysis cancelled")
        if time.monotonic() >= self.deadline:
            raise AnalysisTimedOut("Analysis timed out")

    def advance(self, completed, total):
        self.checkpoint()
        self.progress(completed, total)
