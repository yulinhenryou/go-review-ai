# Migration from the Prototype

*Written 2026-11-03 from a read-through of the prototype at commit `eb089bc`
(branch `codex/m5-deployment`). Nothing listed here has been executed yet; every
status is **Planned** until the owner approves M0.*

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

### 3.1 Before the move

1. Owner accepts the Xcode license on the development Mac (git currently fails).
2. Tag commit: `eb089bc` (owner confirmed 2026-11-03, ADR-P14). It is the
   `codex/m5-deployment` head and, per the local remote-tracking ref, also
   `origin/main`; the local `main` branch is behind at `bf002e0`.
3. Annotated tag `v0.1.0-prototype` on that commit, pushed. The existing tag
   `archive/prototype-2026-08-27` (on `7447f54`, the pre-M1 prototype) stays.
4. Fast-forward local `main` to the tagged commit and start M0 on a branch.

### 3.2 What moves into `legacy/` (with `git mv`, so history follows)

`src/`, `app/`, `frontend/`, `tests/`, `scripts/`, `samples/`, `config/`,
`deploy/`, `archive/`, `Dockerfile`, `.dockerignore`, `pyproject.toml`,
`constraints.txt`, `.env.example`, `Start Go Review.command`,
`Stop Go Review.command`, the old `README.md` (→ `legacy/README.md`), and all
existing `docs/*` files and `docs/evidence/` (→ `legacy/docs/`).

All prototype paths are relative to the project root (`samples/…`,
`docs/evidence/m3-report.json`, `Path(__file__).parents[1]`), so moving the whole
tree together keeps them valid when commands run from `legacy/`.

### 3.3 What stays at the root

`licenses/KATAGO_NETWORK_LICENSE.txt` (still applies), `.gitignore` (rewritten,
legacy rules kept under a `legacy/` section), `AGENTS.md` (rewritten as a pointer
to `CLAUDE.md`), and the new documents.

### 3.4 Keeping legacy runnable

- `legacy/` gets its own virtual environment (`legacy/.venv`, ignored) created
  with uv from its existing `pyproject.toml` and `constraints.txt`.
- CI job `legacy`: `cd legacy && pytest -q` (live KataGo cases stay opt-in) and
  `node --test tests/frontend/*.test.mjs`. It must stay green until deletion.
- The local web workspace keeps working via `legacy/Start Go Review.command`.
  The macOS launchd label and paths are recomputed from the new location the
  first time it starts; this is verified in M0.
- The untracked root `.venv/` and `.local/` are removed locally only after the
  legacy environment works and only with the owner's approval.
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
| G01 | `src/game.py` `validate_game` | `crates/weiqi-core/src/rules/` | Rewrite | Turn order, occupied point, simple ko, suicide, two passes; extend with superko, rule sets, setup stones | Planned |
| G02 | `tests/test_game_input.py` (ko and recapture, single/multi-stone suicide, pass handling, coordinate validation, komi validation, immutability) | `crates/weiqi-core/tests/`, Python binding tests | Port | The highest-value test cases in the prototype | Planned |
| G03 | `src/game.py` `validate_komi` (finite, half-point steps, −150…150) | Rust `Rules` + API models | Port | Keep the exact boundary tests | Planned |
| G04 | `GameRecord.missing_fields` and `require_metadata`: rules/komi must be confirmed before analysis | API + web confirm flow | Port | Inherited decision ADR-010 | Planned |
| G05 | `GameRecord.record_status`: a stored result is metadata, not proof the record is complete | Game record model | Port | Small but important honesty rule | Planned |
| G06 | Limits `MAX_SGF_BYTES` 1 MiB, `MAX_MOVES` 500, `MAX_SGF_NODES` 5000 | Core parse limits + API limits | Reference | Re-evaluate for multi-game import | Planned |
| G07 | `src/sgf_parser.py`, `_check_properties` | `crates/weiqi-core/src/sgf/` | Rewrite | New parser supports variations, setup, handicap, encodings, collections; strictness becomes warnings with codes | Planned |
| G08 | `tests/test_sgf_parser.py`, malformed-SGF cases in `tests/test_game_input.py` | Rust SGF tests + fuzz seed corpus | Port | Expected outcomes change where support is added (e.g. `AB`), each change listed in the PR | Planned |
| G09 | `sgfmill` dependency | — | Drop | Removed with `legacy/` | Planned |
| G10 | `src/engine_protocol.py` `sgf_to_gtp` / `gtp_to_sgf` (column I skipped) and `tests/test_katago_client.py::test_coordinate_mapping` | `weiqi-core/src/coord.rs` | Port | Single coordinate authority for all languages | Planned |

### 4.2 Engine integration

| ID | Source | Target | Action | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| E01 | `src/engine_protocol.py` `candidate`, `candidates`, `optional_number` | `python/src/weiqi/engine/parse.py` | Port | Strict parsing: `order`-based ranking, duplicate detection, PV must start with its candidate, finite numbers, winrate in [0,1], booleans rejected | Planned |
| E02 | `src/katago_process.py` `JsonlProcess` | `weiqi/engine/process.py` | Rewrite | asyncio; keep: final-result marker check, unexpected id/turn errors, warnings on `rules`/`komi`/`overrideSettings` are fatal, 4 MiB line limit, stderr drained, cleanup on failure | Planned |
| E03 | `src/katago_client.py` readiness, model/config SHA-256, `-override-config` (BLACK perspective, logging off) | `weiqi/engine/` | Port | Process kept warm across jobs instead of one per game | Planned |
| E04 | `src/katago_client.py` forced played-move search (`allowMoves`) | `weiqi/engine/` | Reference | Needed only for the same-root diagnostic (ADR-P02) | Planned |
| E05 | `src/engine_types.py` `AnalysisEvidence` (version, model id/hash, config hash, visits, request id, turn, root visits, warnings, perspective, unit) | `weiqi/engine/provenance.py` | Port | Extend with `query_key`, overrides, ownership flag, definition ids | Planned |
| E06 | `src/analysis_control.py` cooperative cancel/timeout | asyncio cancellation + KataGo `terminate` | Rewrite | — | Planned |
| E07 | `src/engine_factory.py`: no mock fallback | Engine construction | Keep (principle) | ADR-007 | Planned |
| E08 | `tests/test_katago_client.py` (both perspectives, missing actual move, pass, empty candidates, utility never used as score, invalid fields, order vs array order, negative difference retained, cleanup on protocol error, no local paths in provenance) | `python/tests/engine/` | Port | Rewrite fixtures for the async adapter; keep every assertion's intent | Planned |
| E09 | `tests/fixtures/katago_real_short.json` + `tests/test_recorded_engine.py` | `testdata/engine/` + replay tests | Port | Re-record in the new format with the same sanitising rules | Planned |
| E10 | `tests/mock_engine.py`, `tests/fixtures/jsonl_engine.py` | New async test doubles | Reference | Test-only | Planned |
| E11 | `config/analysis.cfg`, `config/deployment-eigen.cfg` | `config/katago/` | Port | Re-benchmark before changing values | Planned |
| E12 | `scripts/benchmark_engine.py` | `python/src/weiqi/tools/benchmark.py` | Rewrite | Records hardware, engine, model, visits, wall time, peak RSS | Planned |
| E13 | `tests/test_katago_integration.py` (opt-in live: traceable results, passes, end of record, tolerance-based mistake reproduction, progress, cancel reaps engine) | `python/tests/live/` | Port | Same opt-in switch `RUN_KATAGO_INTEGRATION=1` | Planned |

### 4.3 Metrics and report

| ID | Source | Target | Action | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| R01 | `src/mistake_selector.py` `assess_move`: context check (rules, komi, turn, perspective, unit), finite checks, played candidate required, raw vs clamped loss, negative-noise warning | `weiqi/metrics/` | Port | Becomes the same-root definition; sequential added (ADR-P02) | Planned |
| R02 | `src/mistake_severity.py` 3.0 / 5.0 thresholds; `severity_from_loss` (positive loss only) | `weiqi/metrics/severity.py` + calibration table | Port | Values become the default band of a strength-dependent table | Planned |
| R03 | Ranking: unrounded loss desc, then move number; no padding | `weiqi/metrics/` | Port | ADR-004 | Planned |
| R04 | `limit` restricted to 1–5 | — | Rewrite | Configurable limit; full chronological list always available | Planned |
| R05 | `tests/test_mistake_selector.py`, `tests/test_review_result.py` (threshold boundaries, ties, no padding, missing scores, winrate cannot promote severity, incomparable context rejected, non-finite rejected, pass not missing, both colors agree with black-perspective chart) | `python/tests/metrics/` | Port | — | Planned |
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
| D03 | `licenses/KATAGO_NETWORK_LICENSE.txt` | root `licenses/` | Keep | — | Planned |
| D04 | `samples/sample_game.sgf`, `samples/m3_mistake.sgf` (synthetic) | `testdata/sgf/` | Keep | Copy with provenance | Planned |
| D05 | `samples/benchmark_pro_game.sgf` (235 moves, from Sabaki's public test fixture, normalised) | `testdata/sgf/` | Keep | Provenance in `samples/README.md` is carried over | Planned |
| D06 | `samples/test_game_kejie.sgf` (111-move main line, 柯洁 vs 王泽锦, with variations; original source not recorded) | `testdata/sgf/` | Keep | Owner approved public use on 2026-11-03; it is the real game the prototype was demonstrated on and a comparison-suite input | Planned |
| D07 | `tests/fixtures/m4-*.sgf` | `testdata/sgf/` | Keep | — | Planned |
| D08 | `archive/legacy-reports/` | `legacy/archive/` | Keep (moved) | Deleted with `legacy/`, preserved in tags | Planned |
| D09 | `docs/*.md`, `docs/evidence/` (prototype milestones, contracts, audits) | `legacy/docs/` | Keep (moved) | Decisions summarised in `docs/DECISIONS.md` | Planned |
| D10 | `AGENTS.md` | root | Rewrite | Pointer to `CLAUDE.md` so there is one source of truth; Codex is not in use for now (2026-11-03) but may return | Planned |
| D11 | `README.md` | `legacy/README.md`; root gets `docs/README.draft.md` | Rewrite | After owner approval | Planned |
| D12 | `pyproject.toml`, `constraints.txt` (package names `src`, `app`) | `legacy/` | Keep (moved) | New Python project lives in `python/` | Planned |
| D13 | `.gitignore` | root | Rewrite | Add Rust `target/`, `node_modules/`, web build output, `*.sqlite*`, wasm output, `legacy/.venv/` | Planned |
| D14 | `.env.example` | root | Rewrite | `KATAGO_*` kept; brand-free names | Planned |
| D15 | Untracked `.venv/`, `.local/` (logs) | — | Drop locally | Owner approval required | Planned |

## 5. Status tracking

Update the Status column in the same PR that completes an item: `Planned` →
`In progress` → `Done (commit)` or `Dropped (reason)`. ROADMAP M4's legacy
deletion gate reads this table.
