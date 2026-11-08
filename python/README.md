# Python analysis and service layer

Package `weiqi`: engine adapter, metrics, profile, explanation, training,
storage and API (see `docs/ARCHITECTURE.md`). So far it contains the
project metadata loader and the start of the engine adapter
(`weiqi.engine`): analysis requests validated by the rules core, their
exact-reuse cache key (`query_key`, DECISIONS ADR-P03) and strict parsing of
KataGo analysis responses. It does not start KataGo yet. It depends on `weiqi-core`, the Rust rules core's
binding in `../crates/weiqi-py`, which `uv sync` builds with maturin (a Rust
toolchain is required).

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```
