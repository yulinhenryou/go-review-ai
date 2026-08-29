"""ASGI entry point for the single-origin public service."""
from app.public import build_production_app

app = build_production_app()
