from __future__ import annotations

import json
import os
import selectors
import subprocess
import tempfile
import time

from src.engine_types import EngineProtocolError, KataGoUnavailableError

MAX_LINE_BYTES = 4 * 1024 * 1024


class JsonlProcess:
    """One POSIX subprocess, bounded nonblocking pipes, ID/turn matched replies."""

    def __init__(self, command: list[str]) -> None:
        self._directory = tempfile.TemporaryDirectory(prefix="go-review-engine-")
        self._selector = selectors.DefaultSelector()
        self._buffer = bytearray()
        self._process = None
        self._closed = False
        try:
            self._process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, bufsize=0, cwd=self._directory.name,
            )
            for pipe in (self._process.stdin, self._process.stdout, self._process.stderr):
                os.set_blocking(pipe.fileno(), False)
            self._selector.register(self._process.stdout, selectors.EVENT_READ, "stdout")
            self._selector.register(self._process.stderr, selectors.EVENT_READ, "stderr")
        except (OSError, ValueError) as exc:
            self.close()
            raise KataGoUnavailableError("Cannot start the configured KataGo binary") from exc

    @property
    def pid(self) -> int:
        return self._process.pid

    def exchange(
        self, requests: list[dict], expected: set[tuple[str, int | None]], timeout: float,
    ) -> tuple[dict[tuple[str, int | None], dict], tuple[str, ...]]:
        if self._closed:
            raise KataGoUnavailableError("Engine session is closed")
        pending = bytearray("".join(json.dumps(q, allow_nan=False) + "\n" for q in requests).encode())
        results = {}
        warnings = set()
        ids = {key[0] for key in expected}
        deadline = time.monotonic() + timeout
        self._selector.register(self._process.stdin, selectors.EVENT_WRITE, "stdin")
        try:
            while len(results) < len(expected) or pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise KataGoUnavailableError("KataGo analysis timed out")
                if self._process.poll() is not None:
                    raise KataGoUnavailableError("KataGo exited before completing analysis")
                for key, _mask in self._selector.select(min(remaining, 0.25)):
                    if key.data == "stdin":
                        written = os.write(key.fd, pending[:65536])
                        del pending[:written]
                        if not pending:
                            self._selector.unregister(self._process.stdin)
                        continue
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        self._selector.unregister(key.fileobj)
                        if key.data == "stdout":
                            raise KataGoUnavailableError("KataGo closed its output before completion")
                        continue
                    if key.data == "stderr":
                        # Drain diagnostics without retaining private paths or game inputs.
                        continue
                    self._buffer.extend(chunk)
                    while b"\n" in self._buffer:
                        line, _, rest = self._buffer.partition(b"\n")
                        self._buffer = bytearray(rest)
                        if len(line) > MAX_LINE_BYTES:
                            raise EngineProtocolError("Engine response exceeds size limit")
                        if not line.strip():
                            continue
                        try:
                            message = json.loads(line, parse_constant=_invalid_constant)
                        except (ValueError, UnicodeError) as exc:
                            raise EngineProtocolError("Malformed engine JSONL") from exc
                        if not isinstance(message, dict):
                            raise EngineProtocolError("Engine response must be an object")
                        if "error" in message:
                            raise EngineProtocolError("KataGo rejected the analysis request")
                        request_id = message.get("id")
                        if not isinstance(request_id, str) or request_id not in ids:
                            raise EngineProtocolError("Unexpected engine response ID")
                        if "warning" in message:
                            if message.get("field") in {"rules", "komi", "overrideSettings"}:
                                raise EngineProtocolError("KataGo cannot honor the requested analysis settings")
                            warnings.add("engine_warning")
                            continue
                        turn = message.get("turnNumber")
                        if turn is not None and (type(turn) is not int or turn < 0):
                            raise EngineProtocolError("Invalid response turn number")
                        response_key = (request_id, turn)
                        if response_key not in expected:
                            raise EngineProtocolError("Unexpected response turn number")
                        if turn is not None:
                            if message.get("isDuringSearch") is True:
                                continue
                            if message.get("isDuringSearch") is not False:
                                raise EngineProtocolError("Analysis response lacks a final-result marker")
                        if response_key in results:
                            raise EngineProtocolError("Duplicate final engine response")
                        results[response_key] = message
                    if len(self._buffer) > MAX_LINE_BYTES:
                        raise EngineProtocolError("Unterminated engine response exceeds size limit")
            return results, tuple(sorted(set(warnings)))
        except OSError as exc:
            self.close()
            raise KataGoUnavailableError("KataGo pipe communication failed") from exc
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        try:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe is not None:
                        pipe.close()
        finally:
            self._selector.close()
            self._directory.cleanup()


def _invalid_constant(_value: str):
    raise ValueError("Nonfinite JSON value")
