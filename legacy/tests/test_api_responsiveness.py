import asyncio
import threading

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from src.engine_types import KataGoUnavailableError


def test_upload_analysis_does_not_block_health_requests():
    entered = threading.Event()
    release = threading.Event()

    def slow_engine_factory():
        entered.set()
        release.wait(timeout=2)
        raise KataGoUnavailableError("Intentional test failure")

    async def check():
        async with AsyncClient(transport=ASGITransport(app=create_app(slow_engine_factory)),
                               base_url="http://local.test") as client:
            analysis = asyncio.create_task(client.post("/api/v1/analyze-sgf", files={
                "file": ("test.sgf", b"(;GM[1]FF[4]SZ[19]RU[Chinese]KM[7.5];B[pd])"),
            }))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                assert not analysis.done(), "analysis blocked the event loop"
                health = await asyncio.wait_for(client.get("/health"), timeout=.5)
                assert health.json() == {"status": "ok"}
            finally:
                release.set()
                result = await analysis
            assert result.status_code == 503
            assert result.json()["error"]["code"] == "engine_unavailable"

    asyncio.run(check())
