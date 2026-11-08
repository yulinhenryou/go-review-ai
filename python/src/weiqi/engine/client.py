"""The KataGo engine: one warm process, its identity, and restarts (MIGRATION E03, E05).

`KataGoEngine` starts `katago analysis` once and keeps it running across
games (the prototype started a process per game). Before the first query it
checks readiness: the engine must report a version and exactly one loaded
model, and the model and config files are hashed with SHA-256. Those facts
form the `EngineIdentity` that every result and cache key carries.

Restarts are lazy: if the process has died, the next call starts a new one.
Pending queries of a dead process fail with `engine_unavailable` instead of
being retried, so a caller never receives results from two processes as one
answer. Failed starts back off exponentially.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from weiqi.engine.errors import EngineProtocolError, EngineUnavailableError
from weiqi.engine.identity import EngineIdentity
from weiqi.engine.process import EngineProcess, EngineReply, new_query_id
from weiqi.engine.response import TurnAnalysis, parse_turn
from weiqi.engine.settings import EngineSettings, restart_delay

if TYPE_CHECKING:
    from pathlib import Path

    from weiqi.engine.request import AnalysisRequest, JsonScalar

BASE_OVERRIDES: Final[tuple[tuple[str, JsonScalar], ...]] = (
    ("logAllRequests", False),
    ("logAllResponses", False),
    ("logErrorsAndWarnings", False),
    ("logToStderr", False),
    ("reportAnalysisWinratesAs", "BLACK"),
)
"""Settings forced on the command line whatever the config file says: values
in BLACK perspective, and no logs that could hold games or paths."""

_VERSION = re.compile(r"[0-9A-Za-z._+-]{1,80}")
_MODEL_NAME = re.compile(r"[0-9A-Za-z._+-]{1,200}")


@dataclass(frozen=True, slots=True)
class TurnResult:
    """One analysed turn with what is needed to store and reuse it."""

    analysis: TurnAnalysis
    query_key: str
    engine_warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GameAnalysis:
    """The answer to one request, with its provenance (MIGRATION E05)."""

    request: AnalysisRequest
    identity: EngineIdentity
    query_id: str
    results: tuple[TurnResult, ...]
    """One per `request.analyze_turns`, in that order."""
    elapsed_seconds: float
    raw_perspective: Literal["BLACK"] = "BLACK"


def _override_text(overrides: tuple[tuple[str, JsonScalar], ...]) -> str:
    def text(value: JsonScalar) -> str:
        return ("true" if value else "false") if isinstance(value, bool) else str(value)

    return ",".join(f"{name}={text(value)}" for name, value in overrides)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_files(model: Path, config: Path) -> tuple[str, str]:
    """SHA-256 of the model and config. Blocking; run it in a thread."""
    try:
        for path in (model, config):
            if not path.is_file() or path.stat().st_size == 0:
                raise EngineUnavailableError(
                    "engine_files_missing", "the model or config file is missing or empty"
                )
        return _sha256(model), _sha256(config)
    except OSError as error:
        raise EngineUnavailableError(
            "engine_files_missing", "the model or config file cannot be read"
        ) from error


def _identity(
    version_reply: dict[str, object],
    models_reply: dict[str, object],
    model_sha256: str,
    config_sha256: str,
) -> EngineIdentity:
    version = version_reply.get("version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise EngineProtocolError("invalid_version", "the engine reported no valid version")
    models = models_reply.get("models")
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict):
        raise EngineProtocolError("invalid_models", "expected exactly one loaded model")
    name = models[0].get("internalName")
    if not isinstance(name, str) or not _MODEL_NAME.fullmatch(name):
        raise EngineProtocolError("invalid_models", "the engine reported no valid model name")
    return EngineIdentity(
        version=version,
        model_name=name,
        model_sha256=model_sha256,
        config_sha256=config_sha256,
        overrides=BASE_OVERRIDES,
    )


class KataGoEngine:
    """A supervised KataGo analysis engine. Use `async with KataGoEngine(...)`."""

    def __init__(self, settings: EngineSettings) -> None:
        self._settings = settings
        self._process: EngineProcess | None = None
        self._identity: EngineIdentity | None = None
        self._lock = asyncio.Lock()
        self._failed_starts = 0
        self._closed = False
        self._starts = 0
        self._queries = 0

    @property
    def starts(self) -> int:
        """Processes started so far (1 unless the engine was restarted)."""
        return self._starts

    @property
    def queries(self) -> int:
        """Analysis queries sent to the engine so far."""
        return self._queries

    @property
    def pid(self) -> int | None:
        """For tests and diagnostics only; never part of provenance."""
        return self._process.pid if self._process is not None else None

    async def start(self) -> EngineIdentity:
        """Starts the engine if it is not running and returns its identity."""
        async with self._lock:
            return await self._ensure_running()

    async def readiness(self) -> dict[str, str]:
        """What the engine reports about itself; holds no file paths."""
        identity = await self.start()
        return {
            "status": "ready",
            "engine": "KataGo",
            "version": identity.version,
            "model_name": identity.model_name,
            "model_sha256": identity.model_sha256,
            "config_sha256": identity.config_sha256,
        }

    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        timeout: float | None = None,
        on_turn: Callable[[TurnResult], None] | None = None,
    ) -> GameAnalysis:
        """Analyses every turn in `request` with one query.

        `timeout` defaults to `turn_timeout` per analysed turn. Cancelling
        the calling task terminates the query and keeps the engine running.
        """
        async with self._lock:
            identity = await self._ensure_running()
            process = self._process
        assert process is not None
        if timeout is None:
            timeout = self._settings.turn_timeout * len(request.analyze_turns)
        results: dict[int, TurnResult] = {}

        def on_reply(reply: EngineReply) -> None:
            result = TurnResult(
                analysis=parse_turn(reply.payload, request, reply.turn),
                query_key=request.query_key(identity, reply.turn),
                engine_warnings=reply.warnings,
            )
            results[reply.turn] = result
            if on_turn is not None:
                on_turn(result)

        query_id = new_query_id()
        started = time.monotonic()
        self._queries += 1
        try:
            await process.analyze(request.to_query(query_id), timeout=timeout, on_reply=on_reply)
        except EngineProtocolError:
            # Content that does not fit the request: stop trusting this process.
            await self._retire(process)
            raise
        return GameAnalysis(
            request=request,
            identity=identity,
            query_id=query_id,
            results=tuple(results[turn] for turn in request.analyze_turns),
            elapsed_seconds=time.monotonic() - started,
        )

    async def _ensure_running(self) -> EngineIdentity:
        if self._closed:
            raise EngineUnavailableError("engine_unavailable", "the engine was closed")
        if self._process is not None and self._process.alive and self._identity is not None:
            return self._identity
        if self._process is not None:
            await self._retire(self._process)
        settings = self._settings
        await asyncio.sleep(
            restart_delay(
                self._failed_starts, settings.restart_base_delay, settings.restart_max_delay
            )
        )
        try:
            async with asyncio.timeout(settings.startup_timeout):
                self._process, self._identity = await self._launch()
        except TimeoutError:
            self._failed_starts += 1
            raise EngineUnavailableError(
                "engine_unavailable", "engine start-up timed out"
            ) from None
        except BaseException:
            self._failed_starts += 1
            raise
        self._failed_starts = 0
        self._starts += 1
        return self._identity

    async def _launch(self) -> tuple[EngineProcess, EngineIdentity]:
        settings = self._settings
        binary = shutil.which(settings.katago_path)
        if binary is None:
            raise EngineUnavailableError("engine_not_found", "the KataGo binary was not found")
        model, config = settings.model_path.resolve(), settings.config_path.resolve()
        model_sha256, config_sha256 = await asyncio.to_thread(_hash_files, model, config)
        command = [
            binary,
            "analysis",
            "-model",
            str(model),
            "-config",
            str(config),
            "-override-config",
            _override_text(BASE_OVERRIDES),
        ]
        process = await EngineProcess.start(command, max_in_flight=settings.max_in_flight)
        try:
            identity = _identity(
                await process.request("query_version"),
                await process.request("query_models"),
                model_sha256,
                config_sha256,
            )
        except BaseException:
            await process.close()
            raise
        return process, identity

    async def _retire(self, process: EngineProcess) -> None:
        if self._process is process:
            self._process = None
            self._identity = None
        await process.close()

    async def close(self) -> None:
        """Stops the engine; later calls raise `engine_unavailable`."""
        self._closed = True
        if self._process is not None:
            await self._retire(self._process)

    async def __aenter__(self) -> KataGoEngine:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()
