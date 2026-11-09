"""Metric-layer errors. Each carries a stable machine-readable `code`."""

from __future__ import annotations


class MetricInputError(ValueError):
    """Evaluations or settings that metrics must not be computed from."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
