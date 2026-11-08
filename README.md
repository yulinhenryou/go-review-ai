# Fupan

Fupan is a Go (Weiqi / Baduk) game-review project: it turns a player's own games
into a diagnosis and a training plan.

> **Status: early development, under active rebuild.** There is no usable
> release of the new design yet. The "Vision" section describes goals, not
> shipped features.

*Fupan is a provisional name.* It comes from 复盘 (fùpán), the Go tradition of
replaying a finished game to find where it was won and lost.

## Where this project comes from

This repository started as **Go Review AI**, an early experiment that reviewed a
single game with KataGo: SGF parsing and validation, real KataGo analysis with
recorded provenance, mistake selection by estimated point loss, short factual
Chinese summaries, a FastAPI service and a browser board with progress and
cancellation.

That prototype is preserved under the Git tag
[`v0.1.0-prototype`](https://github.com/yulinhenryou/go-review-ai/tree/v0.1.0-prototype)
and, during the rebuild, runs unchanged from the [`legacy/`](legacy/README.md)
directory with its own environment. It will be removed from the main tree only
after the new implementation matches it in comparison tests; it always remains
available in Git history.

## Vision

Single-game "which move lost the most points" is already well served by tools
such as KaTrain. Fupan aims at the questions that come after:

1. **Player profile** — across many games, where are the points lost: by phase
   (opening, middle game, endgame) and by situation (life and death, invasion,
   ko, endgame), with trends and confidence intervals.
2. **Explanations with reasons** — built only from engine evidence (variations,
   score and ownership change, which group's status changed), in Chinese and
   English with standard Go terminology. No invented reasoning.
3. **Closed-loop training** — mistakes from your own games become exercises,
   scheduled with spaced repetition, and progress is measured again in later games.
4. **Calibrated to your level** — what counts as a mistake, and what an
   explanation emphasises, depends on the player's strength.

Fupan is not a playing engine, does not train neural networks, and does not try
to compete with Sabaki or KaTrain as a board editor.

More: [Vision](docs/VISION.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Roadmap](docs/ROADMAP.md) · [Decisions](docs/DECISIONS.md) ·
[Migration](docs/MIGRATION.md)

## Repository layout

| Path | Contents | State |
| --- | --- | --- |
| `crates/weiqi-core/` | Rust rules core (rules, SGF, Zobrist hashing, scoring) | Implemented in M1 |
| `crates/weiqi-py/` | Python binding (PyO3), module `weiqi_core` | Built in M2; scoring not exposed yet |
| `crates/weiqi-wasm/` | WebAssembly binding (wasm-bindgen) for the web app | Built in M2; used by the web app |
| `python/` | Python analysis and service layer, package `weiqi` | M3: KataGo adapter, analysis cache (SQLite / PostgreSQL), fixture recorder, benchmark |
| `web/` | TypeScript + React + Vite app | M2 shell: manual entry and SGF replay through the WASM core |
| `testdata/sgf/` | Public SGF test corpus with provenance | — |
| `testdata/conformance/` | Golden cases shared by the Rust core and its bindings | Rust, Python and WASM runners (M2) |
| `testdata/engine/` | Recorded real KataGo exchanges for replay tests | One short game (M3) |
| `config/katago/` | KataGo analysis config (no model weights) | Copied from the prototype (M3) |
| `config/project.json` | The single source of the provisional project name | — |
| `legacy/` | The Go Review AI prototype | Runs and is tested in CI |
| `docs/` | Vision, architecture, roadmap, decisions, migration, acceptance records | — |

The Rust core reaches Python through PyO3 (`uv sync` in `python/` builds it
with maturin, so a Rust toolchain is required) and the browser through
WebAssembly (`npm run wasm` in `web/` builds it into `web/src/wasm/`). Analysis uses the
[KataGo](https://github.com/lightvector/KataGo) analysis engine (M3).

## Development

Toolchains: Rust via rustup (version pinned in `rust-toolchain.toml`), Python via
[uv](https://docs.astral.sh/uv/) (version pinned in `python/.python-version`),
Node.js 22.12 or later.

```bash
cargo fmt --all -- --check && cargo clippy --workspace --all-targets -- -D warnings && cargo test --workspace
```

Benchmarks: `cargo bench -p weiqi-core`. Fuzzing needs the nightly toolchain
and [cargo-fuzz](https://github.com/rust-fuzz/cargo-fuzz); run it from
`crates/weiqi-core/fuzz/`, which selects nightly itself:

```bash
cd crates/weiqi-core/fuzz && cargo fuzz run parse -- -max_total_time=60
```

```bash
cd python && uv sync && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

The binding's stub is checked against the built module from `python/`:

```bash
uv run python -m mypy.stubtest weiqi_core --allowlist ../crates/weiqi-py/stubtest-allowlist.txt
```

The web app needs the WASM build first, which needs the `wasm-bindgen` CLI at
the same version as the crate:

```bash
cargo install wasm-bindgen-cli@0.2.130 --locked
```

```bash
cd web && npm ci && npm run wasm && npm run lint && npm run typecheck && npm test && npm run build
```

The prototype keeps its own instructions in [legacy/README.md](legacy/README.md).
KataGo binaries and network weights are not part of this repository.

## Current status

M0 (archive, legacy move, monorepo skeleton, CI) is recorded in
[docs/acceptance/M0.md](docs/acceptance/M0.md). M1 (Rust rules engine, scoring
and SGF parser) is recorded in [docs/acceptance/M1.md](docs/acceptance/M1.md). M2 (Python and WebAssembly
bindings, a web shell for manual entry and SGF replay, browser end-to-end
tests) is recorded in [docs/acceptance/M2.md](docs/acceptance/M2.md). M3 (KataGo analysis engine
adapter, analysis cache and storage, live tests and benchmarks) is recorded
in [docs/acceptance/M3.md](docs/acceptance/M3.md). Progress continues milestone by
milestone in the [roadmap](docs/ROADMAP.md); this README states only facts
that have been tested.

## Licence

[Apache License 2.0](LICENSE). KataGo and its networks are separate projects
under their own licences; see [the KataGo network licence](licenses/KATAGO_NETWORK_LICENSE.txt).
