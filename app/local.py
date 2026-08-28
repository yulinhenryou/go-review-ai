"""Checkout-only local app: serve the UI and API from one loopback origin."""
import hashlib
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
app = create_app()


@app.middleware("http")
async def no_local_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/local-status")
def local_status():
    return {"application": "go-review-ai-local", "project_id": PROJECT_ID}


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
