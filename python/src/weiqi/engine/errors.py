"""Engine-layer errors. Each carries a stable machine-readable `code`."""

from __future__ import annotations


class EngineError(Exception):
    """Base class for errors raised by the engine layer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InvalidRequestError(EngineError, ValueError):
    """An analysis request that must not be sent to the engine."""


class EngineProtocolError(EngineError):
    """Engine output that is malformed or does not match its request."""


class EngineUnavailableError(EngineError):
    """The engine cannot be started, or stopped while queries were pending."""


class EngineRejectedError(EngineError):
    """The engine refused a query, or warned that it cannot honour a setting
    (rules, komi or override settings) that the results would depend on."""


class EngineTimeoutError(EngineError):
    """A query did not finish in time; it has been terminated."""
