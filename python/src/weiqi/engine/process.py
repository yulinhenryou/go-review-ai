"""One KataGo analysis-engine process spoken to over JSON lines (MIGRATION E02, E06).

A single reader task reads the engine's stdout and routes each reply by
query id (and, for analysis, by turn) to the coroutine waiting for it.
Another task reads stderr and throws it away, so that pipe never fills up and
private paths in the engine's diagnostics never reach our logs.

Any reply that breaks the protocol (bad JSON, an unknown id or turn, a
missing final-result marker, a line over the size limit) ends the process:
every waiter fails with `EngineProtocolError`, because once the stream is out
of step no later reply can be trusted. If the process exits, every waiter
fails with `EngineUnavailableError`. Restarting is the supervisor's job.

Cancelling or timing out an analysis sends KataGo's `terminate` action for
that query. Its late replies, which may carry partial results, are ignored.

An optional transcript callback sees every message written and every JSON
object read, in order. It exists for recording public test fixtures and for
live tests that check what the engine actually said.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
import uuid
from asyncio.subprocess import PIPE
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from weiqi.engine.errors import (
    EngineError,
    EngineProtocolError,
    EngineRejectedError,
    EngineTimeoutError,
    EngineUnavailableError,
)

LINE_LIMIT: Final = 4 * 1024 * 1024
"""The longest reply line accepted, in bytes."""

FATAL_WARNING_FIELDS: Final = frozenset({"rules", "komi", "overrideSettings"})
"""Fields whose warnings mean the results would not answer the request."""

type Transcript = Callable[[Literal["sent", "received"], Mapping[str, object]], None]
"""Sees each message sent to and each JSON object received from the engine.
It runs inside the reader and writer, so it must be quick and must not raise."""


@dataclass(frozen=True, slots=True)
class EngineReply:
    """The final reply for one turn of an analysis query."""

    turn: int
    payload: Mapping[str, object]
    warnings: tuple[str, ...]
    """Fields the engine warned about for this query (non-fatal ones)."""


@dataclass(slots=True)
class _Analysis:
    expected: frozenset[int]
    queue: asyncio.Queue[EngineReply | EngineError] = field(default_factory=asyncio.Queue)
    received: set[int] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    def fail(self, error: EngineError) -> None:
        self.queue.put_nowait(error)


@dataclass(slots=True)
class _Action:
    future: asyncio.Future[dict[str, object]]

    def fail(self, error: EngineError) -> None:
        if not self.future.done():
            self.future.set_exception(error)


def new_query_id() -> str:
    """A fresh, unguessable query id."""
    return uuid.uuid4().hex


def _reject_constant(name: str) -> object:
    raise ValueError(f"non-finite JSON constant {name}")


class EngineProcess:
    """A running engine. Create one with `await EngineProcess.start(...)`."""

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        workdir: tempfile.TemporaryDirectory[str],
        max_in_flight: int,
        transcript: Transcript | None = None,
    ) -> None:
        self._process = process
        self._transcript = transcript
        self._workdir = workdir
        self._slots = asyncio.Semaphore(max_in_flight)
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, _Analysis | _Action] = {}
        # Ids whose replies are no longer wanted: terminated or rejected
        # queries, and the echoes of our terminate actions.
        self._ignored: set[str] = set()
        self._failure: EngineError | None = None
        self._closed = False
        self._reader = asyncio.create_task(self._read_stdout())
        self._drainer = asyncio.create_task(self._drain_stderr())

    @classmethod
    async def start(
        cls,
        command: Sequence[str],
        *,
        max_in_flight: int = 1,
        line_limit: int = LINE_LIMIT,
        transcript: Transcript | None = None,
    ) -> EngineProcess:
        """Starts `command` in an empty temporary working directory, so the
        engine cannot write files into the repository."""
        if type(max_in_flight) is not int or max_in_flight < 1:
            raise ValueError("max_in_flight must be a positive integer")
        workdir = tempfile.TemporaryDirectory(prefix="weiqi-engine-")
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=workdir.name, limit=line_limit
            )
        except (OSError, ValueError) as error:
            workdir.cleanup()
            # The message names no path: provenance and logs stay path-free.
            raise EngineUnavailableError(
                "engine_unavailable", "the engine could not be started"
            ) from error
        return cls(process, workdir, max_in_flight, transcript)

    @property
    def pid(self) -> int:
        """For tests and diagnostics only; never part of provenance."""
        return self._process.pid

    @property
    def alive(self) -> bool:
        """True until the process fails, exits or is closed."""
        return not self._closed and self._failure is None and self._process.returncode is None

    # --- Requests ---

    async def request(
        self, action: str, *, timeout: float | None = None, **fields: object
    ) -> dict[str, object]:
        """Sends a non-analysis action (e.g. `query_version`) and returns its reply."""
        self._check_alive()
        query_id = new_query_id()
        future: asyncio.Future[dict[str, object]] = asyncio.get_running_loop().create_future()
        self._pending[query_id] = _Action(future)
        try:
            async with asyncio.timeout(timeout):
                await self._send({"id": query_id, "action": action, **fields})
                return await future
        except TimeoutError:
            raise EngineTimeoutError("engine_timeout", f"{action} timed out") from None
        finally:
            if self._pending.pop(query_id, None) is not None and not future.done():
                self._ignored.add(query_id)

    async def analyze(
        self,
        query: Mapping[str, object],
        *,
        timeout: float | None = None,
        on_reply: Callable[[EngineReply], None] | None = None,
    ) -> list[EngineReply]:
        """Sends one analysis query and waits for the final reply of every
        turn in its `analyzeTurns`, returned in turn order.

        `on_reply` sees each reply as it arrives (for progress). Cancelling
        the calling task, or exceeding `timeout`, terminates the query.
        """
        query_id = query.get("id")
        turns = query.get("analyzeTurns")
        if not isinstance(query_id, str) or not query_id:
            raise ValueError("an analysis query needs a string id")
        if query_id in self._pending or query_id in self._ignored:
            raise ValueError("query ids must not be reused within a process")
        if (
            not isinstance(turns, list)
            or not turns
            or any(type(turn) is not int for turn in turns)
            or len(set(turns)) != len(turns)
        ):
            raise ValueError("analyzeTurns must be a non-empty list of distinct integers")

        async with self._slots:
            self._check_alive()
            waiter = _Analysis(expected=frozenset(turns))
            self._pending[query_id] = waiter
            replies: list[EngineReply] = []
            try:
                async with asyncio.timeout(timeout):
                    await self._send(dict(query))
                    while len(replies) < len(waiter.expected):
                        item = await waiter.queue.get()
                        if isinstance(item, EngineError):
                            raise item
                        replies.append(item)
                        if on_reply is not None:
                            on_reply(item)
            except TimeoutError:
                self._abandon(query_id)
                raise EngineTimeoutError("engine_timeout", "the analysis timed out") from None
            except BaseException:
                # Cancellation, an engine error, or an error in on_reply.
                self._abandon(query_id)
                raise
            finally:
                self._pending.pop(query_id, None)
        return sorted(replies, key=lambda reply: reply.turn)

    def _abandon(self, query_id: str) -> None:
        """Stops waiting for a query and asks the engine to stop searching it."""
        if query_id in self._ignored or not self.alive:
            return
        self._ignored.add(query_id)
        terminate_id = new_query_id()
        self._ignored.add(terminate_id)
        self._write({"id": terminate_id, "action": "terminate", "terminateId": query_id})

    def _check_alive(self) -> None:
        if self._closed:
            raise EngineUnavailableError("engine_unavailable", "the engine was closed")
        if self._failure is not None or self._process.returncode is not None:
            raise EngineUnavailableError(
                "engine_unavailable", "the engine is no longer running"
            ) from self._failure

    # --- Writing ---

    def _write(self, message: Mapping[str, object]) -> None:
        stdin = self._process.stdin
        assert stdin is not None  # started with stdin=PIPE
        line = json.dumps(message, allow_nan=False, separators=(",", ":")) + "\n"
        if self._transcript is not None:
            self._transcript("sent", message)
        # If the process is gone, the reader reports the exit.
        with contextlib.suppress(ConnectionError, RuntimeError):
            stdin.write(line.encode("utf-8"))

    async def _send(self, message: Mapping[str, object]) -> None:
        stdin = self._process.stdin
        assert stdin is not None
        async with self._send_lock:
            self._write(message)
            try:
                await stdin.drain()
            except ConnectionError as error:
                raise EngineUnavailableError(
                    "engine_unavailable", "the engine stopped reading its input"
                ) from error

    # --- Reading ---

    async def _read_stdout(self) -> None:
        stdout = self._process.stdout
        assert stdout is not None
        try:
            while True:
                try:
                    line = await stdout.readline()
                except ValueError:
                    raise EngineProtocolError(
                        "line_too_long", "an engine reply exceeds the line limit"
                    ) from None
                if not line:
                    break
                if line.strip():
                    self._dispatch(line)
        except EngineProtocolError as error:
            self._fail(error)
            return
        except Exception as error:  # a bug here must not leave waiters hanging
            self._fail(EngineProtocolError("reader_failed", f"reading replies failed: {error!r}"))
            raise
        self._fail(EngineUnavailableError("engine_unavailable", "the engine exited"))

    async def _drain_stderr(self) -> None:
        stderr = self._process.stderr
        assert stderr is not None
        while await stderr.read(65536):
            pass

    def _dispatch(self, line: bytes) -> None:
        try:
            message = json.loads(line, parse_constant=_reject_constant)
        except ValueError:  # also covers UnicodeDecodeError
            raise EngineProtocolError("invalid_json", "an engine reply is not JSON") from None
        if not isinstance(message, dict):
            raise EngineProtocolError("invalid_json", "an engine reply is not a JSON object")
        if self._transcript is not None:
            self._transcript("received", message)
        query_id = message.get("id")
        if isinstance(query_id, str) and query_id in self._ignored:
            return
        waiter = self._pending.get(query_id) if isinstance(query_id, str) else None
        if waiter is None:
            what = "error" if "error" in message else "reply"
            raise EngineProtocolError("unexpected_id", f"an engine {what} matches no query")
        assert isinstance(query_id, str)
        field = message.get("field")
        field_name = field if isinstance(field, str) else "unknown"

        if "error" in message:
            self._ignored.add(query_id)
            waiter.fail(
                EngineRejectedError("engine_rejected", f"the engine rejected field {field_name}")
            )
            return
        if "warning" in message:
            if field_name in FATAL_WARNING_FIELDS:
                # KataGo keeps searching after a warning; stop it, since the
                # results would not answer the request.
                self._abandon(query_id)
                waiter.fail(
                    EngineRejectedError("engine_warning", f"the engine cannot honour {field_name}")
                )
            elif isinstance(waiter, _Analysis):
                waiter.warnings.append(field_name)
            return

        if isinstance(waiter, _Action):
            if not waiter.future.done():
                waiter.future.set_result(message)
            return
        turn = message.get("turnNumber")
        if type(turn) is not int or turn not in waiter.expected:
            raise EngineProtocolError("unexpected_turn", "a reply has an unrequested turn")
        during_search = message.get("isDuringSearch")
        if during_search is True:
            return  # a progress report; only final results are used
        if during_search is not False:
            raise EngineProtocolError("missing_final_marker", "a reply lacks isDuringSearch")
        if turn in waiter.received:
            raise EngineProtocolError("duplicate_reply", "a turn was answered twice")
        if message.get("noResults") is True:
            # Only a terminated query may end without results.
            raise EngineProtocolError("no_results", "a running query returned no results")
        waiter.received.add(turn)
        waiter.queue.put_nowait(EngineReply(turn, message, tuple(waiter.warnings)))

    # --- Failure and shutdown ---

    def _fail_waiters(self, error: EngineError) -> None:
        for waiter in list(self._pending.values()):
            waiter.fail(error)

    def _fail(self, error: EngineError) -> None:
        """Records the first failure, fails every waiter and stops the process."""
        if self._failure is None and not self._closed:
            self._failure = error
        self._fail_waiters(error)
        self._kill()

    def _kill(self) -> None:
        if self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._process.kill()

    async def close(self, grace: float = 2.0) -> None:
        """Stops the engine: closes its input, waits `grace` seconds for it to
        exit, then kills it. Pending queries fail with `engine_unavailable`."""
        if self._closed:
            return
        self._closed = True
        self._fail_waiters(EngineUnavailableError("engine_unavailable", "the engine was closed"))
        stdin = self._process.stdin
        if stdin is not None and not stdin.is_closing():
            stdin.close()
        try:
            await asyncio.wait_for(self._process.wait(), grace)
        except TimeoutError:
            self._kill()
            await self._process.wait()
        for task in (self._reader, self._drainer):
            with contextlib.suppress(Exception):  # already reported to the waiters
                await task
        self._workdir.cleanup()

    async def __aenter__(self) -> EngineProcess:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()
