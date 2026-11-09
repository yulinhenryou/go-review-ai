# Migration from the Prototype

*Written 2026-11-03 from a read-through of the prototype at commit `eb089bc`
(tag `v0.1.0-prototype`). Statuses are updated as items complete; M0 completed
the repository-level moves in §3 and the D-items marked Done.*

## 1. Principles

- The prototype is a behavioral baseline, not a design constraint.
- Ideas, metric definitions and test cases are worth more than code. Most code
  is rewritten; most test cases are ported.
- New code never imports from `legacy/`. The legacy tree runs in its own
  environment until it is deleted.
- Nothing is lost: the prototype stays reachable through tags and history.

## 2. Actions

| Action | Meaning |
| --- | --- |
| **Keep** | Carry the file over unchanged (possibly to a new path) |
| **Reference** | Consult while designing; no code carried over |
| **Port** | Translate the logic or test cases faithfully into the new layer and language |
| **Rewrite** | Same responsibility, new design; behavior may intentionally differ |
| **Drop** | Not carried forward; remains in history |

## 3. The `legacy/` transition

### 3.1 Before the move (done 2026-11-03)

1. Xcode license accepted on the development Mac (git had been failing).
2. Tag commit `eb089bc` (ADR-P14): the `codex/m5-deployment` head and `origin/main`.
3. Annotated tag `v0.1.0-prototype` on that commit. The existing tag
   `archive/prototype-2026-08-27` (on `7447f54`, the pre-M1 prototype) stays.
4. Local `main` fast-forwarded to `eb089bc`; M0 work on `rebuild/m0-foundation`.

### 3.2 What moved into `legacy/` (with `git mv`, so history follows)

`src/`, `app/`, `frontend/`, `tests/`, `scripts/`, `samples/`, `config/`,
`deploy/`, `archive/`, `Dockerfile`, `.dockerignore`, `pyproject.toml`,
`constraints.txt`, `.env.example`, `.gitignore`, `AGENTS.md`, `licenses/`,
`Start Go Review.command`,
`Stop Go Review.command`, the old `README.md` (→ `legacy/README.md`), and all
existing `docs/*` files and `docs/evidence/` (→ `legacy/docs/`).

All prototype paths are relative to the project root (`samples/…`,
`docs/evidence/m3-report.json`, `Path(__file__).parents[1]`), so moving the whole
tree together keeps them valid when commands run from `legacy/`.

### 3.3 What the root has instead

A copy of `licenses/KATAGO_NETWORK_LICENSE.txt` (the legacy deployment test
reads its own copy), a new monorepo `.gitignore`, a one-line `AGENTS.md`
pointing to `CLAUDE.md`, the new README and documents, and the new skeleton.

### 3.4 Keeping legacy runnable

- `legacy/` has its own virtual environment (`legacy/.venv`, ignored), created
  with uv (Python 3.14) from its `pyproject.toml` and `constraints.txt`.
- CI job `legacy` runs its pytest suite (live KataGo cases skipped) and
  `node --test tests/frontend/*.test.mjs`. It must stay green until deletion.
- M0 verified the web app from `legacy/` by running `uvicorn app.local:app` with
  the launcher's engine environment: the UI was served and a real KataGo review
  completed. The launcher derives its launchd label from the checkout path, so
  it now reports a new project id; starting it through launchd
  (`legacy/Start Go Review.command`) was not exercised in M0.
- Root `.local/` (old server logs) moved to `legacy/.local/`; the stale root
  `.venv/` was removed after the legacy environment passed its tests.
- Legacy is frozen: only changes needed to keep it running are allowed.

### 3.5 Deleting `legacy/` (end of M4)

Delete in one commit only when all of the following hold (see ROADMAP M4):

1. Every item in §4 marked Port or Rewrite is Done or explicitly Dropped.
2. The comparison suite (ROADMAP M4) passes against the legacy pipeline.
3. The new web review page covers the legacy browser workflow.
4. The owner approves.

## 4. Item list

Source paths are pre-M0 locations. Targets use the layout in ARCHITECTURE §2.

### 4.1 Game input and rules

| ID | Source | Target | Action | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| G01 | `src/game.py` `validate_game` | `crates/weiqi-core/src/{board,rules,game}.rs` | Rewrite | Turn order, occupied point, simple ko, suicide, two passes; extend with superko, rule sets, setup stones | Done (M1, 59b995a, 863ac83) |
| G02 | `tests/test_game_input.py` (ko and recapture, single/multi-stone suicide, pass handling, coordinate validation, komi validation, immutability) | `crates/weiqi-core/tests/`, Python binding tests | Port | The highest-value test cases in the prototype | Done (Rust tests in M1: 59b995a, 863ac83, a009265; Python binding tests in M2: daa0d4f) |
| G03 | `src/game.py` `validate_komi` (finite, half-point steps, −150…150) | Rust `Rules` + API models | Port | Keep the exact boundary tests | In progress (Rust `Komi` done in M1, 863ac83; API models later) |
| G04 | `GameRecord.missing_fields` and `require_metadata`: rules/komi must be confirmed before analysis | API + web confirm flow | Port | Inherited decision ADR-010 | In progress (M1 extraction leaves unconfirmed rules and komi as `None`, a009265; API and confirm flow later) |
| G05 | `GameRecord.record_status`: a stored result is metadata, not proof the record is complete | Game record model | Port | Small but important honesty rule | Planned |
| G06 | Limits `MAX_SGF_BYTES` 1 MiB, `MAX_MOVES` 500, `MAX_SGF_NODES` 5000 | Core parse limits + API limits | Reference | Re-evaluate for multi-game import | In progress (core `ParseLimits` in M1, 23ec86b: defaults 16 MiB, 1,000,000 nodes, depth 10,000; API limits later) |
| G07 | `src/sgf_parser.py`, `_check_properties` | `crates/weiqi-core/src/sgf/` | Rewrite | New parser supports variations, setup, handicap, encodings, collections; strictness becomes warnings with codes | Done (M1, 23ec86b, a009265) |
| G08 | `tests/test_sgf_parser.py`, malformed-SGF cases in `tests/test_game_input.py` | Rust SGF tests + fuzz seed corpus | Port | Expected outcomes change where support is added (e.g. `AB`), each change listed in the PR | Done (M1, 23ec86b, a009265; the fuzz runs are seeded with `testdata/sgf/`) |
| G09 | `sgfmill` dependency | — | Drop | Removed with `legacy/` | Planned |
| G10 | `src/engine_protocol.py` `sgf_to_gtp` / `gtp_to_sgf` (column I skipped) and `tests/test_katago_client.py::test_coordinate_mapping` | `weiqi-core/src/coord.rs` | Port | Single coordinate authority for all languages | Done (M1, 59b995a) |

### 4.2 Engine integration

| ID | Source | Target | Action | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| E01 | `src/engine_protocol.py` `candidate`, `candidates`, `optional_number` | `python/src/weiqi/engine/response.py` | Port | Strict parsing: `order`-based ranking, duplicate detection, PV must start with its candidate, finite numbers, winrate in [0,1], booleans rejected | In progress (M3 step 1: parsing ported; GTP conversion now comes from the core) |
| E02 | `src/katago_process.py` `JsonlProcess` | `weiqi/engine/process.py` | Rewrite | asyncio; keep: final-result marker check, unexpected id/turn errors, warnings on `rules`/`komi`/`overrideSettings` are fatal, 4 MiB line limit, stderr drained, cleanup on failure | Done in M3 step 2 (asyncio `EngineProcess`; all listed behaviours kept and tested against a fake engine) |
| E03 | `src/katago_client.py` readiness, model/config SHA-256, `-override-config` (BLACK perspective, logging off) | `weiqi/engine/client.py` | Port | Process kept warm across jobs instead of one per game | Done in M3 step 3 (`KataGoEngine`: warm process, readiness, SHA-256 identity, forced overrides, lazy restart with backoff) |
| E04 | `src/katago_client.py` forced played-move search (`allowMoves`) | `weiqi/engine/` | Reference | Needed only for the same-root diagnostic (ADR-P02) | Done in M4 step 2 (`AnalysisRequest.played_move_search`, `allowMoves` with `untilDepth` 1, cached under its own `query_key`; chosen by `weiqi.metrics.played_moves_to_search`, sent by `weiqi.review.search_played_moves`; checked live) |
| E05 | `src/engine_types.py` `AnalysisEvidence` (version, model id/hash, config hash, visits, request id, turn, root visits, warnings, perspective, unit) | `weiqi/engine/identity.py`, `weiqi/engine/client.py` (`GameAnalysis`, `TurnResult`) | Port | Extend with `query_key`, overrides, ownership flag, definition ids | Done in M3 step 3 (identity with overrides, query id, per-turn `query_key`, engine warnings, elapsed time, raw perspective; ownership flag in the request) |
| E06 | `src/analysis_control.py` cooperative cancel/timeout | asyncio cancellation + KataGo `terminate` | Rewrite | — | Done in M3 step 2 (cancellation and timeouts send `terminate`; late replies ignored) |
| E07 | `src/engine_factory.py`: no mock fallback | `weiqi/engine/settings.py` | Keep (principle) | ADR-007 | Done in M3 step 3 (`EngineSettings.from_environment` raises `engine_not_configured`; no fallback) |
| E08 | `tests/test_katago_client.py` (both perspectives, missing actual move, pass, empty candidates, utility never used as score, invalid fields, order vs array order, negative difference retained, cleanup on protocol error, no local paths in provenance) | `python/tests/engine/` | Port | Rewrite fixtures for the async adapter; keep every assertion's intent | Done (M3 steps 1–4; the forced played-move search and score-loss cases in M4 steps 1–2) |
| E09 | `tests/fixtures/katago_real_short.json` + `tests/test_recorded_engine.py` | `testdata/engine/` + replay tests | Port | Re-record in the new format with the same sanitising rules | Done in M3 step 4 (`testdata/engine/short-game.json` from `testdata/sgf/synthetic-short.sgf`, recorded by `weiqi.tools.record_engine`; replayed through the parser and through the whole client) |
| E10 | `tests/mock_engine.py`, `tests/fixtures/jsonl_engine.py` | `python/tests/engine/fake_katago.py` | Reference | Test-only | Done in M3 step 2 (a JSON-lines fake engine with one misbehaviour per mode; test-only) |
| E11 | `config/analysis.cfg`, `config/deployment-eigen.cfg` | `config/katago/` | Port | Re-benchmark before changing values | In progress (M3 step 3: `analysis.cfg` copied unchanged to `config/katago/`; `deployment-eigen.cfg` waits for deployment in M8) |
| E12 | `scripts/benchmark_engine.py` | `python/src/weiqi/tools/benchmark.py` | Rewrite | Records hardware, engine, model, visits, wall time, peak RSS | Done in M3 step 6 (`weiqi.tools.benchmark`: cold and warm process per visit count, each in a fresh worker process; also times a fully cached re-analysis; results in `docs/acceptance/M3.md`) |
| E13 | `tests/test_katago_integration.py` (opt-in live: traceable results, passes, end of record, tolerance-based mistake reproduction, progress, cancel reaps engine) | `python/tests/live/` | Port | Same opt-in switch `RUN_KATAGO_INTEGRATION=1` | Done in M3 step 4 for the engine layer (traceable results, passes and end of record under two rule sets, progress per turn, the 235-move game, cancel keeps the process usable, kill and restart, Black perspective of winrate, score and ownership); tolerance-based mistake reproduction moves to M4 with the metrics |

### 4.3 Metrics and report

| ID | Source | Target | Action | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| R01 | `src/mistake_selector.py` `assess_move`: context check (rules, komi, turn, perspective, unit), finite checks, played candidate required, raw vs clamped loss, negative-noise warning | `weiqi/metrics/` | Port | Becomes the same-root definition; sequential added (ADR-P02) | Done in M4 steps 1–2 (sequential and same-root loss with raw values, noise, missing-evidence, `separate_search` and `low_visits` flags; context checked through `query_key`) |
| R02 | `src/mistake_severity.py` 3.0 / 5.0 thresholds; `severity_from_loss` (positive loss only) | `weiqi/metrics/severity.py` + calibration table | Port | Values become the default band of a strength-dependent table | Done in M4 step 1 (`weiqi.metrics.severity`: calibration table with one default band, 4.0 / 8.0 per ADR-P17; boundaries tested for it and for the prototype's 3.0 / 5.0) |
| R03 | Ranking: unrounded loss desc, then move number; no padding | `weiqi/metrics/` | Port | ADR-004 | Done in M4 step 1 (`weiqi.metrics.selection`) |
| R04 | `limit` restricted to 1–5 | — | Rewrite | Configurable limit; full chronological list always available | Done in M4 step 1 (optional positive `limit`; no upper bound; selection never pads) |
| R05 | `tests/test_mistake_selector.py`, `tests/test_review_result.py` (threshold boundaries, ties, no padding, missing scores, winrate cannot promote severity, incomparable context rejected, non-finite rejected, pass not missing, both colors agree with black-perspective chart) | `python/tests/metrics/` | Port | — | In progress (M4 step 1: the `test_mistake_selector.py` cases, plus checks against the recorded real exchange; the `test_review_result.py` cases come with the result schema in step 4) |
| R06 | `src/review_result.py` schema 3.0: coverage (missing move numbers, partial vs complete), method block, timeline vs ranked selection, black-perspective chart fields | `weiqi/metrics/result.py` | Rewrite | Keep the concepts; remove embedded Chinese strings | Planned |
| R07 | `src/report_writer.py` templates and `QUALITY_NOTES` | `weiqi/explain/locales/zh-CN` + `en` | Port | Text becomes catalog entries keyed by codes | Planned |
| R08 | `src/analyzer.py`, `src/review_service.py`, `src/main.py` | `weiqi/review/` + CLI | Rewrite | Keep a CLI as a development entry point | Planned |
| R09 | Retired `src/key_points.py` (history only): turning points via winrate cliff, near-losing transition, clustering radius | `weiqi/metrics/turning_points.py` | Reference | Redefine numerically and version it; do not copy thresholds | Planned |
| R10 | Retired `src/classifier.py`, `chinese_explanations.py`, `user_facing_labels.py` (history only) | — | Drop | Inferred causes from distance, move number and candidate rank; not engine-backed | Planned |

### 4.4 API, jobs and service

| ID | Source | Target | Action | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| A01 | `app/jobs.py` semantics: bounded queue, states, stable input snapshot, cancel releases capacity, retention, result size budget, legacy endpoints share capacity | `weiqi/api/jobs.py` | Port (semantics) / Rewrite (code) | Persistent jobs, asyncio worker | Planned |
| A02 | `tests/test_jobs.py`, `tests/test_api.py`, `tests/test_input_api.py`, `tests/test_api_responsiveness.py` | `python/tests/api/` | Port | — | Planned |
| A03 | `app/models.py`: Pydantic `extra="forbid"`, `strict=True`, `allow_inf_nan=False` | API models | Port | — | Planned |
| A04 | Error body `{detail, error: {code, message, field, move_number}}`; no echo of raw input | API errors | Port | — | Planned |
| A05 | `app/limits.py` body limit (incl. chunked), `no-store` | API middleware | Port | — | Planned |
| A06 | `app/settings.py` exact-origin CORS validation | API settings | Port | Drop the `GO_REVIEW_` prefix | Planned |
| A07 | `app/public.py` (host check, rate limits, security headers), `tests/test_public.py` | M8 deployment | Reference | — | Planned |
| A08 | `app/local.py`, `scripts/local_server.py`, `.command` launchers, launchd plist | Dev scripts | Drop | Replaced by documented dev commands | Planned |

### 4.5 Frontend

| ID | Source | Target | Action | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| F01 | `frontend/input-state.mjs` revision token (late responses ignored) | `web/` state | Port (pattern) | — | Planned |
| F02 | `frontend/review-navigation.mjs`: post-game position distinct from last move | `web/` | Port | With its tests | Planned |
| F03 | `frontend/game-settings.mjs`: presets (Chinese 7.5, Japanese 6.5), custom komi requires confirmation | `web/` | Port | — | Planned |
| F04 | `frontend/board-markers.mjs`, `board-view.mjs`: distinct mistake / recommendation / candidate markers, one marker per point | `web/` board | Reference | Visual design is redone | Planned |
| F05 | `frontend/job-client.mjs`: polling, refresh recovery, cancel after failed poll | `web/` | Reference | SSE replaces polling | Planned |
| F06 | `frontend/review-controller.mjs` (962 lines), `app.mjs`, `index.html`, `styles.css` | — | Drop | Rewritten in React | Planned |
| F07 | `tests/frontend/*.test.mjs` (40 cases) | Vitest | Port | Cases that encode behavior, not DOM details | Planned |
| F08 | `frontend/icons/` (Lucide v0.468.0, ISC) | `web/` | Reference | Use the maintained package or keep files with licence | Planned |
| F09 | `frontend/demo-app.mjs`, `demo-data.json`, `scripts/build_pages.py`, `gh-pages` showcase | — | Drop (for new code) | The `gh-pages` branch is left untouched until M8 | Planned |

### 4.6 Deployment, data and repository files

| ID | Source | Target | Action | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| D01 | `Dockerfile` (pinned digests, KataGo source build with SHA-256 check, model hash check, licence copy) | M8 container | Reference | — | Planned |
| D02 | `deploy/fly.toml`, `scripts/deploy_fly.sh`, `scripts/*acceptance*` | M8 | Reference | — | Planned |
| D03 | `licenses/KATAGO_NETWORK_LICENSE.txt` | root `licenses/` | Keep | — | Done (M0, root copy kept; legacy keeps its own) |
| D04 | `samples/sample_game.sgf`, `samples/m3_mistake.sgf` (synthetic) | `testdata/sgf/` | Keep | Copy with provenance | Planned |
| D05 | `samples/benchmark_pro_game.sgf` (235 moves, from Sabaki's public test fixture, normalised) | `testdata/sgf/` | Keep | Provenance in `samples/README.md` is carried over | Done (M1, a009265, as `testdata/sgf/maruyama-ito-1976.sgf`) |
| D06 | `samples/test_game_kejie.sgf` (111-move main line, 柯洁 vs 王泽锦, with variations; original source not recorded) | `testdata/sgf/` | Keep | Owner approved public use on 2026-11-03; it is the real game the prototype was demonstrated on and a comparison-suite input | Done (M1, a009265, as `testdata/sgf/kejie-2025-11-27.sgf`) |
| D07 | `tests/fixtures/m4-*.sgf` | `testdata/sgf/` | Keep | — | Planned |
| D08 | `archive/legacy-reports/` | `legacy/archive/` | Keep (moved) | Deleted with `legacy/`, preserved in tags | Done (M0) |
| D09 | `docs/*.md`, `docs/evidence/` (prototype milestones, contracts, audits) | `legacy/docs/` | Keep (moved) | Decisions summarised in `docs/DECISIONS.md` | Done (M0) |
| D10 | `AGENTS.md` | root | Rewrite | Pointer to `CLAUDE.md` so there is one source of truth; Codex is not in use for now (2026-11-03) but may return | Done (M0) |
| D11 | `README.md` | `legacy/README.md`; root gets the new README | Rewrite | After owner approval | Done (M0) |
| D12 | `pyproject.toml`, `constraints.txt` (package names `src`, `app`) | `legacy/` | Keep (moved) | New Python project lives in `python/` | Done (M0) |
| D13 | `.gitignore` | root | Rewrite | Add Rust `target/`, `node_modules/`, web build output, `*.sqlite*`, wasm output, `legacy/.venv/` | Done (M0) |
| D14 | `.env.example` | root | Rewrite | `KATAGO_*` kept; brand-free names | Planned (M3, when the service has settings) |
| D15 | Untracked `.venv/`, `.local/` (logs) | — | Drop locally | Owner approval required | Done (M0; `.local/` moved to `legacy/.local/`, root `.venv/` removed) |

## 5. Status tracking

Update the Status column in the same PR that completes an item: `Planned` →
`In progress` → `Done (commit)` or `Dropped (reason)`. ROADMAP M4's legacy
deletion gate reads this table.
