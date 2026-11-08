"""L1 engine adapter: KataGo analysis requests, responses and provenance."""

from weiqi.engine.errors import (
    EngineError,
    EngineProtocolError,
    EngineRejectedError,
    EngineTimeoutError,
    EngineUnavailableError,
    InvalidRequestError,
)
from weiqi.engine.identity import EngineIdentity
from weiqi.engine.request import AnalysisRequest
from weiqi.engine.response import (
    Candidate,
    RootInfo,
    TurnAnalysis,
    parse_turn,
    score_for,
    winrate_for,
)

__all__ = [
    "AnalysisRequest",
    "Candidate",
    "EngineError",
    "EngineIdentity",
    "EngineProtocolError",
    "EngineRejectedError",
    "EngineTimeoutError",
    "EngineUnavailableError",
    "InvalidRequestError",
    "RootInfo",
    "TurnAnalysis",
    "parse_turn",
    "score_for",
    "winrate_for",
]
