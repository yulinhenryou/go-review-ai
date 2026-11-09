# Python analysis and service layer

Package `weiqi`: engine adapter, metrics, profile, explanation, training,
storage and API (see `docs/ARCHITECTURE.md`). So far it contains the
project metadata loader and the start of the engine adapter
(`weiqi.engine`): analysis requests validated by the rules core, their
exact-reuse cache key (`query_key`, DECISIONS ADR-P03) and strict parsing of
KataGo analysis responses, and an asyncio process layer that speaks the
analysis engine's JSON-lines protocol (routing, cancellation, timeouts,
failure handling), tested against a fake engine; and `KataGoEngine`, which
keeps one KataGo process warm, checks its readiness and identity, and
analyses a whole game per query. It needs a local KataGo:
`KATAGO_MODEL_PATH` (required), `KATAGO_PATH` and `KATAGO_CONFIG_PATH`
(default `config/katago/analysis.cfg`). `weiqi.tools.record_engine` records
a public record's real engine exchange as a test fixture (see
`../testdata/engine/README.md`), and `weiqi.tools.benchmark` times a
whole-game analysis with a cold and a warm engine process
(`docs/acceptance/M3.md` records how it was run). `weiqi.storage` keeps analysed turns in
SQLite or PostgreSQL (SQLAlchemy Core and Alembic) so that `CachedAnalyzer`
asks the engine only for turns it has not stored; create or update a
database with `uv run python -m weiqi.storage.migrate upgrade sqlite:///weiqi.db`.
The storage tests use SQLite, and also PostgreSQL when `TEST_POSTGRESQL_URL`
names a database they may empty (CI provides one). `weiqi.metrics` computes
per-move score loss and winrate change from stored evaluations (the sequential
and same-root definitions of ADR-P02), severity from a calibration table
(ADR-P17) and the ranked mistake list; `weiqi.review` runs the restricted
searches of played moves that the same-root values need. It depends on `weiqi-core`, the Rust rules core's
binding in `../crates/weiqi-py`, which `uv sync` builds with maturin (a Rust
toolchain is required).

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Live tests against the real KataGo are opt-in. On 2026-11-08 they took 76 s
on the owner's Apple M4 with the b18 model, 57 s of it for the 235-move game
at 32 visits (pytest `--durations`, not a benchmark):

```bash
RUN_KATAGO_INTEGRATION=1 KATAGO_MODEL_PATH=/path/to/model.bin.gz uv run pytest tests/live
```
