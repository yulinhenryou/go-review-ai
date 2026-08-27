# Project Status Audit

## M1 Update

The user approved implementation on 2026-08-27. M1 now provides validated shared
input records, sgfmill parsing/captures, explicit rules/komi confirmation, input
size limits, pass/current-position separation and packaged installation.
See [M1 acceptance](M1_ACCEPTANCE.md) and [the input contract](INPUT_CONTRACT.md).
Real-engine evaluation correctness, mock isolation and report teaching remain
M2/M3 work; public hosting remains M5 work.

## Historical M0 Audit

Date: 2026-08-27. Baseline: `7447f54688f45d3783e41b633663e760a8aa061e`.
The findings below describe that baseline, not the current M1 implementation.
They are retained as historical evidence, not a v1 acceptance report.

## Verified in This Pass

- Fetched `origin`; the local and remote `main` were at the same baseline.
- Ran `.venv/bin/python -m pytest -q -ra`: 54 passed, no skipped tests reported.
- Retrieved the public Pages HTML and compared SHA-256 with `frontend/index.html`:
  both were `70ca673ceeb0b2f2aed966e0f68b41e88fe9a0a44f049b0aae6135aaafe19174`.
- Traced imports and sample-file references before selecting archive candidates.
- Found a local KataGo executable, but did not run a model/config validation,
  benchmark, real-engine analysis, clean install, or browser interaction test.

## Release Blockers

| Priority | Evidence in current code | Why it blocks v1 | Planned owner |
| --- | --- | --- | --- |
| Critical | `src/katago_client.py::_resolve_played_candidate` subtracts 0.3 score and 0.02 winrate from the last candidate if the played move is absent | A fabricated evaluation can be presented as a real mistake | M2 |
| Critical | The same function treats `played_move=None` as the best move; `None` is also pass | Passing is not actually evaluated as a distinct action | M1/M2 |
| Critical | `_to_candidate` accepts `utility` in place of `scoreLead`, defaults missing winrate to 0.5; `_pv_summary_from_katago` can assemble a sequence from alternative candidates and pad missing moves with passes | Different units and invented data can enter a report | M2 |
| Critical | Engine queries do not fix `reportAnalysisWinratesAs`; analysis subtracts raw candidate scores | Black/white perspective and loss signs are not guaranteed by the adapter | M2 |
| High | `src/main.py::build_default_engine` substitutes `MockEngineClient` when environment configuration is missing; API results lack engine provenance | Users cannot reliably distinguish a demonstration from a real analysis | M2/M4 |
| High | `src/sgf_parser.py::parse_sgf` reads limited root metadata and moves only after the root; `ParsedGame` has no rules or setup fields; engine queries hardcode Japanese rules | Root-node moves can be dropped; SGF rules, setup stones and turn information can be lost | M1 |
| High | SGF and JSON inputs follow different validators; backend does not replay legality | Illegal moves and unsupported games may reach the engine or be misrepresented | M1 |
| High | `KataGoClient::_run_query` starts a process per position and takes only the last output line; `analyze_game_state` makes N+1 calls | Repeated model startup and inadequate response matching impede full-game analysis | M2 |
| High | `app/main.py::analyze_sgf` calls blocking analysis inside an async route; no upload/move limits or bounded jobs | Long games can block the service or consume unbounded resources | M1/M4 |
| High | `frontend/index.html` targets `127.0.0.1:8000`; `app/main.py` allows only `http://localhost:3000` | The Pages preview is not a working public analysis service | M4/M5 |
| High | `src/classifier.py` infers causes from distance, move number and rank; `src/key_points.py` and templates add teaching narratives | Deterministic prose is not necessarily an engine-supported Go explanation | M3 |
| Medium | `frontend/index.html` is 2,638 lines with board logic, API calls, state, templates and styles mixed together | UI changes are difficult to test or isolate | M4 |
| Medium | `tests/test_frontend_board_demo.py` asserts HTML/JS strings; engine tests use mocks | Passing tests do not demonstrate browser interaction or real-engine correctness | M2/M4/M5 |
| Medium | Dependencies are unpinned; `pyproject.toml` lacks an explicit package build/discovery configuration | Installation reproducibility is not yet established | M1 |

These are code-inspection findings except where explicitly labeled as verified
above. There is no claim that every failure has been reproduced with a live engine.

## Retention Decisions

All Python modules under `src/` are referenced by the current application or test
suite. `app/` and `frontend/` are the only existing browser workflow. Moving these
directories wholesale would break the prototype and is not housekeeping.

The two stored sample reports have no runtime/test consumers and are stale output
snapshots. In particular, the text snapshot describes a four-move example as
having a middle game and endgame. Archive them without changing their bytes; do
not treat them as engine evidence or as golden tests.

Retain both SGF inputs. `sample_game.sgf` is used by tests; `test_game_kejie.sgf`
is an optional manual sample with variations and imperfect metadata, not an
acceptance fixture. See [sample notes](../samples/README.md).

The complete pre-cleanup source remains in baseline commit `7447f54` on GitHub
and the local `archive/prototype-2026-08-27` tag. The active mock/heuristic code is **not yet
removed**: M2 and M3 must replace those paths and verify compatibility first.
There is no newly introduced production path in this housekeeping change.

## History and Deployment

Terminal HTTPS push was rejected with an invalid username/token; no usable SSH
agent identity was available. The connected GitHub account could read the repository,
but its tree-creation request was rejected with HTTP 403, "Resource not accessible
by integration." No housekeeping changes or archive tag have been uploaded.
Restore repository write authentication before synchronizing. Terminal credentials
also need renewal for future `git push` operations. Use the baseline commit link in
[the archive index](../archive/README.md) for the online source snapshot.

Runtime logs were untracked in commit `7447f54` and remain locally ignored. They
still exist in older Git commits. This pass does not purge history or claim to
remove those historical files from GitHub.

The `gh-pages` branch has its own `.nojekyll` commit after the earlier subtree
publication. Do not assume a new `git subtree push` from `main` can fast-forward
it; do not solve publication conflicts with an unreviewed force push. A tested
release process is part of M5. The current publication stays unchanged.
