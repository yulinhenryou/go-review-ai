"""Production-only HTTP boundaries and application assembly."""
from collections import deque
import hashlib
import ipaddress
import math
from pathlib import Path
import secrets
import threading
import time

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


EXPENSIVE_REQUESTS = {
    ("GET", "/ready"),
    ("POST", "/api/v1/jobs"),
    ("POST", "/api/v1/analyze-sgf"),
    ("POST", "/api/v1/analyze-moves"),
}

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; connect-src 'self'; img-src 'self'; style-src 'self'; "
        "script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'none'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class SlidingWindowLimit:
    """Small in-memory limiter sized for one public application process."""

    def __init__(self, *, window: int, client_limit: int, global_limit: int, clock=time.monotonic):
        if not 1 <= window <= 86400 or not 1 <= client_limit <= global_limit <= 10000:
            raise ValueError("Invalid public rate-limit settings")
        self.window = window
        self.client_limit = client_limit
        self.global_limit = global_limit
        self.clock = clock
        self.global_events = deque()
        self.client_events = {}
        self.lock = threading.Lock()

    def admit(self, client_key: bytes) -> tuple[bool, int]:
        now = self.clock()
        cutoff = now - self.window
        with self.lock:
            while self.global_events and self.global_events[0] <= cutoff:
                self.global_events.popleft()
            for key, events in list(self.client_events.items()):
                while events and events[0] <= cutoff:
                    events.popleft()
                if not events:
                    del self.client_events[key]

            events = self.client_events.get(client_key)
            blocked_until = []
            if len(self.global_events) >= self.global_limit:
                blocked_until.append(self.global_events[0] + self.window)
            if events is not None and len(events) >= self.client_limit:
                blocked_until.append(events[0] + self.window)
            if blocked_until:
                return False, max(1, math.ceil(min(blocked_until) - now))

            self.global_events.append(now)
            self.client_events.setdefault(client_key, deque()).append(now)
            return True, 0


class PublicProtectionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        hosts: tuple[str, ...],
        client_ip_header: str | None,
        rate_window: int,
        client_limit: int,
        global_limit: int,
    ) -> None:
        self.app = app
        self.hosts = set(hosts)
        self.client_ip_header = client_ip_header.encode() if client_ip_header else None
        self.limiter = SlidingWindowLimit(
            window=rate_window, client_limit=client_limit, global_limit=global_limit,
        )
        self._client_salt = secrets.token_bytes(32)

    @staticmethod
    def _headers(scope: Scope) -> dict[bytes, bytes]:
        headers = {}
        for key, value in scope.get("headers", []):
            key = key.lower()
            # Duplicate routing/proxy headers are ambiguous. Empty values fail
            # Host validation and collapse client limiting to the unknown bucket.
            headers[key] = b"" if key in headers and key in {b"host", b"fly-client-ip"} else value
        return headers

    def _client_key(self, scope: Scope, headers: dict[bytes, bytes]) -> bytes:
        raw = headers.get(self.client_ip_header, b"") if self.client_ip_header else b""
        if not raw:
            raw = str((scope.get("client") or ("unknown", 0))[0]).encode()
        try:
            canonical = ipaddress.ip_address(raw.decode("ascii")).compressed.encode()
        except (UnicodeDecodeError, ValueError):
            canonical = b"unknown"
        return hashlib.blake2s(canonical, key=self._client_salt, digest_size=16).digest()

    @staticmethod
    async def _send_json(response: JSONResponse, scope: Scope, receive: Receive, send: Send) -> None:
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = self._headers(scope)
        try:
            host = headers.get(b"host", b"").decode("ascii").lower()
        except UnicodeDecodeError:
            host = ""
        if scope["path"] != "/health" and host not in self.hosts:
            response = JSONResponse(
                {"detail": "Invalid request host", "error": {
                    "code": "invalid_host", "message": "Invalid request host",
                }},
                status_code=400,
            )
            await self._send_json(response, scope, receive, send)
            return

        if (scope["method"], scope["path"]) in EXPENSIVE_REQUESTS:
            accepted, retry_after = self.limiter.admit(self._client_key(scope, headers))
            if not accepted:
                response = JSONResponse(
                    {"detail": "Public analysis limit reached; try again later", "error": {
                        "code": "rate_limited",
                        "message": "Public analysis limit reached; try again later",
                    }},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
                await self._send_json(response, scope, receive, send)
                return

        async def secure_send(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    response_headers[name] = value
            await send(message)

        await self.app(scope, receive, secure_send)


def build_production_app(engine_factory=None, *, options=None):
    """Serve the frontend and API on one origin with public-only controls."""
    from fastapi.staticfiles import StaticFiles

    from app.main import create_app
    from app.settings import public_options

    selected = options or public_options()
    app = create_app(engine_factory=engine_factory, public=True)
    app.add_middleware(
        PublicProtectionMiddleware,
        hosts=selected["hosts"],
        client_ip_header=selected["client_ip_header"],
        rate_window=selected["rate_window"],
        client_limit=selected["client_limit"],
        global_limit=selected["global_limit"],
    )

    @app.get("/release")
    def release():
        return {
            "application": "go-review-ai",
            "release": selected["release"],
            "storage": "ephemeral-memory",
            "engine": "real-katago",
        }

    root = Path(__file__).resolve().parents[1]
    app.mount("/", StaticFiles(directory=root / "frontend", html=True), name="frontend")
    return app
