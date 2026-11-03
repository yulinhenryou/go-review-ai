# Python analysis and service layer

Package `weiqi`: engine adapter, metrics, profile, explanation, training,
storage and API (see `docs/ARCHITECTURE.md`). M0 contains only the project
metadata loader.

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```
