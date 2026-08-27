# go-review-ai

A Go game review prototype built around KataGo. The first release is intended to
turn an uploaded SGF or a manually entered game into a short, evidence-based web
report highlighting obvious mistakes.

**Current status: M2 real-engine integration verified, not a validated v1.**
SGF/manual inputs share a validated model; real KataGo analysis now has explicit
provenance and no mock fallback. Concise factual reporting and public deployment
remain M3-M5 work. See [M2 acceptance](docs/M2_ACCEPTANCE.md).

## What It Does

The target v1 workflow is:

**Upload SGF / enter moves on a board -> validate the game -> analyze with KataGo
-> identify obvious mistakes -> show a concise report in the browser.**

The prototype already contains SGF main-line parsing, a KataGo subprocess client,
mistake ranking, structured JSON and text reports, a FastAPI API, and a browser
board with SGF upload and move navigation. These are implementation starting
points, not proof of a reliable review service.

V1 will focus on one 19x19 game at a time. Each reported mistake should include
the move number, player, actual move, recommendation, estimated score loss, and a
short factual explanation. No accounts, database, LLM commentary, or automated
claims about tactical causes are required for this release.

## Tech Stack

| Layer | Current implementation |
| --- | --- |
| Core | Python 3.11+, dataclasses, standard library |
| Game input | sgfmill 1.1.1, immutable game records, shared replay validation and strict JSON models |
| Analysis | External KataGo; one loaded process per game, bounded JSONL batches and evidence normalization |
| API | FastAPI, Pydantic, Uvicorn, python-multipart |
| Frontend | HTML, CSS, vanilla JavaScript, Canvas 2D |
| Tests | pytest, HTTPX, protocol subprocess fixtures, recorded real responses and opt-in live KataGo tests |
| Static preview | GitHub Pages, published from `gh-pages` |

KataGo models and executables are not bundled. There is no deployed Python backend
in this repository's Pages site. sgfmill supplies parsing and captures; the app
enforces the supported turn, suicide and simple-ko policy.

## How It Works

```text
SGF upload -----------------> SGF parser ----+
                                            |
Manual board -> JSON moves -> API models ----+-> GameRecord + shared validation
                                                 |
                                           analysis pipeline
                                                 |
                                           engine adapter
                                                 |
                                     score loss / mistake selection
                                                 |
                                    structured review + text templates
                                                 |
                                          API JSON -> browser
```

The CLI and API share review functions in `src/review_service.py`. The current pipeline
also runs experimental classification and teaching heuristics. V1 will remove
unsupported teaching claims from the default report, preserving the old prototype
in the [archive](archive/README.md).

### Repository Layout

| Path | Responsibility |
| --- | --- |
| `src/game.py` | Shared game records, limits, legality replay and input previews |
| `src/sgf_parser.py` | Strict sgfmill adapter and metadata extraction |
| `src/katago_client.py` | Real-engine lifecycle, batched queries and played-move evaluation |
| `src/katago_process.py`, `src/engine_protocol.py`, `src/engine_types.py` | Bounded JSONL transport, strict value mapping and evidence types |
| `src/engine_factory.py` | Explicit real-engine configuration; no mock fallback |
| `src/analyzer.py` | Position-by-position analysis orchestration |
| `src/mistake_selector.py`, `src/mistake_severity.py` | Mistake ranking and severity |
| `src/classifier.py`, `src/key_points.py` | Experimental heuristics, still called by the prototype |
| `src/review_result.py` | Structured result contract and serialization |
| `src/report_writer.py`, `src/chinese_explanations.py`, `src/user_facing_labels.py` | Report templates and labels |
| `src/review_service.py` | Shared review orchestration |
| `src/main.py` | Sample CLI and legacy builder re-exports |
| `app/` | FastAPI routes and request models |
| `frontend/` | Current browser prototype and Pages publication source |
| `tests/` | Regression tests, isolated mock fixtures and recorded real-engine evidence |
| `config/analysis.cfg`, `scripts/benchmark_engine.py` | Local engine baseline and opt-in performance measurement |
| `samples/` | Sample SGF inputs; see [sample notes](samples/README.md) |
| `docs/` | Contracts, acceptance evidence, status audit and approved roadmap |
| `archive/` | Historical output snapshots and prototype archive index; not runtime code |

### Run the Current Prototype

Run commands from the repository root. For a fresh environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints.txt -e '.[api,dev]'
python -m pytest -q -ra
```

Direct dependencies and build tooling are pinned in `pyproject.toml`;
`constraints.txt` records tested transitive versions. Editable and regular wheel
installation were verified in a fresh environment on macOS arm64 / Python 3.14.4.
Other Python/platform combinations are not yet an acceptance matrix.
The wheel contains only Python packages, not archives, samples, tests or frontend
files. Use the repository checkout for the sample CLI and browser UI.

**Real engine required:** the CLI/API fail explicitly without a usable KataGo,
model and configuration. Mock output is now confined to test fixtures. The
legacy report still contains heuristic teaching prose pending M3; do not treat
those narratives as established tactical explanations.

For the real engine, install KataGo and obtain a compatible model and analysis
config following the [KataGo project](https://github.com/lightvector/KataGo).
Set the environment before starting the CLI or backend:

```bash
export KATAGO_PATH="katago"
export KATAGO_MODEL_PATH="/absolute/path/to/model.bin.gz"
export KATAGO_CONFIG_PATH="$PWD/config/analysis.cfg"
```

Replace the model placeholder with a real local file. Setting paths alone does
not validate the engine. Run the opt-in integration checks and sample CLI:

```bash
RUN_KATAGO_INTEGRATION=1 python -m pytest tests/test_katago_integration.py -q
python -m src.main
```

The tested transport supports macOS/Linux (POSIX); Windows is not verified.

Run the backend:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal with the same environment activated, serve the frontend:

```bash
python -m http.server 3000 --bind 127.0.0.1 --directory frontend
```

Open [http://localhost:3000](http://localhost:3000). Use that exact browser origin:
the current backend CORS allowlist only contains `http://localhost:3000`.
The frontend calls `http://127.0.0.1:8000`; opening it as `file://`, at another
port, or from Pages is not the supported local API configuration.
Choose rules and komi before manual analysis. For SGF uploads, these controls
fill missing metadata only; existing recorded values take precedence.

### Current API

| Endpoint | Input / behavior |
| --- | --- |
| `GET /health` | HTTP liveness only; does not check KataGo readiness |
| `GET /ready` | Fresh real model-load/version check; expensive, not a frequent polling endpoint |
| `POST /api/v1/parse-sgf` | Validated upload preview, no engine; identifies missing metadata |
| `POST /api/v1/validate-moves` | Equivalent preview for manual game JSON, no engine |
| `POST /api/v1/analyze-sgf` | Multipart `file`; `rules`, `komi`, `loss_threshold` and `limit` are query parameters |
| `POST /api/v1/analyze-moves` | Explicit rules/komi and `{color, sgf}` moves; explicit `null` represents pass |

```bash
curl --fail-with-body \
  'http://127.0.0.1:8000/api/v1/analyze-sgf?loss_threshold=3.0&limit=5' \
  -F 'file=@samples/sample_game.sgf'

curl --fail-with-body 'http://127.0.0.1:8000/api/v1/analyze-moves' \
  -H 'Content-Type: application/json' \
  -d '{"board_size":19,"rules":"japanese","komi":6.5,"moves":[{"color":"B","sgf":"pd"},{"color":"W","sgf":"dd"}],"loss_threshold":3.0,"limit":5}'
```

The API returns review schema `2.2`; that number is a data format version,
not a claim that product v2 or v1 is complete. A short sample may have no results
above the example threshold. The proposed v1 threshold is not yet the default.
Preview schema is `1.0`. See [the input contract](docs/INPUT_CONTRACT.md) for
limits, supported SGF properties, error responses and pass semantics.
See [the engine contract](docs/ENGINE_CONTRACT.md) for score perspectives,
candidate PVs, provenance and missing-evidence behavior.

## Current Status

Updated: **2026-08-27**. M2 branch: `codex/m2-engine-reliability`.

| Area | Status and limitation |
| --- | --- |
| SGF input | Shared replay validation, strict limits, metadata confirmation and explicit variation warnings; unsupported setups/rules fail |
| Manual entry | Shared server-side validation and explicit rules/komi; placement/undo/navigation retained; full pass/input UX remains M4 |
| KataGo | Real model readiness, process reuse, strict JSONL matching, explicit played-move search, genuine PVs and fixed-black evidence |
| Mistakes / report | Real numeric evidence; legacy heuristic teaching remains pending M3; incomplete evidence fails clearly instead of fabricating a full report |
| Web service | Input validation and model readiness; bounded background jobs/cancellation still belong to M4 |
| Verification | **225 regular tests passed + 3 opt-in real-engine tests passed**; recorded-response replay and real-model performance checks |
| Deployment | Pages serves the frontend, not a complete online analysis service |

The [Pages preview](https://yulinhenryou.github.io/go-review-ai/) still serves the
older prototype. M0 verified its published HTML; the M1/M2 changes have not been
published to Pages. It targets the visitor's loopback address, and the
Pages origin is absent from the backend's CORS allowlist. Starting a backend on the
developer's computer does not make analysis available to other visitors.

`gh-pages` is a separate publication branch and is **not automatically updated**
by pushing `main`. M1 leaves the deployed prototype unchanged.
See the [detailed status audit](docs/PROJECT_STATUS.md) for evidence and limitations.

## Roadmap

| Milestone | Deliverable | Gate |
| --- | --- | --- |
| M0 | Repository inventory, archive index, README and v1 plan | Complete; housekeeping and archive tag uploaded |
| M1 | Shared validated game model and supported input contract | Complete; 173 tests reverified and main/branch uploaded at d08fc47 |
| M2 | Reliable, efficient real KataGo analysis | Implemented and verified with real models; see acceptance evidence and remaining limits |
| M3 | Obvious-mistake selection and concise factual report | Stable threshold/ranking tests and zero unsupported teaching claims |
| M4 | Complete browser flow with bounded analysis jobs | Upload and manual-entry workflows pass browser acceptance tests |
| M5 | Deployable web release and real-engine acceptance | A second device completes a real game review against the deployed backend |

The next functional milestone is M3: obvious-mistake selection and factual reports.
GitHub terminal write access was restored and verified on 2026-08-27. Keep
[the access recovery guide](docs/GITHUB_AUTH.md) for future credential renewal.

## Development and Archives

- Keep parsing, engine integration, analysis, classification and rendering separate.
- Make one focused change per branch/PR; include relevant tests and verification.
- Keep `main` runnable. Use `codex/` branches for Codex implementation work.
- Do not import from `archive/`, load archived reports as defaults, or publish it.
- Keep runtime logs, private uploads, local configuration and model weights out of Git.
- Preserve historical work through tags and commits; do not rewrite shared history.

The [archive index](archive/README.md) records what was moved, why it was moved,
and which still-active modules need deliberate replacement during v1 development.
