# go-review-ai

A Go game review prototype built around KataGo. The first release is intended to
turn an uploaded SGF or a manually entered game into a short, evidence-based web
report highlighting obvious mistakes.

**Current status: M1-M4 complete; the M5 local candidate and read-only Pages showcase are ready, but this is not a public analysis service or web v1.**
SGF/manual inputs share a validated model; real KataGo analysis now has explicit
provenance and no mock fallback. Reports use point-loss thresholds, top-five
selection, explicit coverage and factual Chinese summaries. The browser now
previews and confirms input, submits bounded cancellable jobs, shows progress,
and restores tasks after page refresh. The repository also contains a pinned
deployment candidate and a static Pages showcase generated from real KataGo
evidence. The owner has chosen local analysis plus Pages presentation for now;
paid hosting and different-network acceptance are deferred.
See [M4 acceptance](docs/M4_ACCEPTANCE.md) and the
[M1-M3 regression record](docs/M1_M3_REGRESSION.md).

## What It Does

The target v1 workflow is:

**Upload SGF / enter moves on a board -> validate the game -> analyze with KataGo
-> identify obvious mistakes -> show a concise report in the browser.**

The prototype already contains SGF main-line parsing, a KataGo subprocess client,
mistake ranking, structured JSON and text reports, a FastAPI API, and a browser
board with SGF preview, manual placement/pass/undo, progress/cancellation and
move navigation. The local workflow is tested; public service acceptance is pending.

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
| API | FastAPI, Pydantic, Uvicorn, python-multipart; one worker and bounded in-memory jobs |
| Frontend | HTML, CSS, vanilla JavaScript, Canvas 2D |
| Tests | pytest, HTTPX, Node test runner, browser acceptance, recorded responses and live KataGo release checks |
| Deployment candidate | Pinned multi-stage Docker image, Fly.io Sydney config, fail-closed readiness and release metadata |
| Static showcase | GitHub Pages, explicit read-only real-engine example published separately from `gh-pages` |

KataGo models and executables are not stored in Git. The M5 image downloads and
hash-verifies pinned official artifacts during its build. There is no deployed Python backend
in this repository's Pages site. sgfmill supplies parsing and captures; the app
enforces the supported turn, suicide and simple-ko policy.

## How It Works

```text
SGF upload -----------------> SGF parser ----+
                                            |
Manual board -> JSON moves -> API models ----+-> GameRecord + shared validation
                                                 |
                                     preview / confirm / bounded job
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

The CLI and API share review functions in `src/review_service.py`. M3 compares
recommendation and actual-move point estimates in the moving player's perspective,
uses 3/5-point obvious/severe thresholds, and ranks up to five mistakes without
rounding before selection. Missing evidence remains explicit. Unsupported
classification/teaching modules are retired; their source remains in Git history
and the [prototype archive tag](archive/README.md).

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
| `src/review_result.py` | Structured result contract and serialization |
| `src/report_writer.py` | Factual Chinese templates and quality notes; no tactical diagnosis |
| `src/review_service.py` | Shared review orchestration |
| `src/main.py` | Sample CLI and legacy builder re-exports |
| `app/` | FastAPI routes, strict models, bounded job manager, retention and origin settings |
| `frontend/` | Separate input state, API/jobs, canvas, review and style modules; explicit Pages demo data/entry |
| `tests/` | Regression tests, isolated mock fixtures and recorded real-engine evidence |
| `config/analysis.cfg`, `scripts/` | Local engine baseline, release checks, Pages build and performance measurement |
| `samples/` | Sample SGF inputs; see [sample notes](samples/README.md) |
| `docs/` | Contracts, acceptance evidence, status audit and approved roadmap |
| `archive/` | Historical output snapshots and prototype archive index; not runtime code |

### Install and Verify

Run commands from the repository root. For a fresh environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints.txt -e '.[api,dev]'
./scripts/release_check.sh
```

Stop the local background service before `release_check.sh`: the live integration
suite starts its own KataGo processes, and Metal model instances should not compete
with the already-running app. Restart the service after the check.

Direct dependencies and build tooling are pinned in `pyproject.toml`;
`constraints.txt` records tested transitive versions. Editable and regular wheel
installation were verified in a fresh environment on macOS arm64 / Python 3.14.4.
Other Python/platform combinations are not yet an acceptance matrix.
The wheel contains only Python packages, not archives, samples, tests or frontend
files. Use the repository checkout for the sample CLI and browser UI.

**Real engine required:** the CLI/API fail explicitly without a usable KataGo,
model and configuration. Mock output is confined to test fixtures. Report
thresholds are configurable product defaults that still need calibration, not
universal Go rules or a claim of search certainty.

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

### Local Web Workspace

On macOS, double-click **Start Go Review.command** in the repository, or run:

```bash
python scripts/local_server.py start --open
```

The launcher starts an on-demand, loopback-only user service. It stays running
after the terminal, browser or Codex conversation closes. It does **not** install
login/startup automation; run the launcher again after logout or reboot.
It uses the existing `.venv` and your configured engine paths. On this tested
Homebrew setup it can also locate the already-installed b18 model and KataGo;
it never downloads a model or substitutes mock analysis.

```bash
python scripts/local_server.py status
python scripts/local_server.py restart
python scripts/local_server.py stop
```

**Stop Go Review.command** stops only this checkout's service. Configuration and
logs are kept in ignored `.local/`, not in Git. Restart after changing Python
code or engine environment variables; refresh the page after frontend changes.

Open [http://localhost:3000](http://localhost:3000). If port 3000 belongs to another
process, the launcher chooses a free port up to 3009 and prints the actual URL.
The frontend and API now share one origin through `app.local:app`; no second
server, hardcoded API port or CORS adjustment is needed. A refused connection
means the launcher must be started, not that a browser proxy must be changed.

For foreground development on macOS/Linux (keep this terminal open):

```bash
python -m uvicorn app.local:app --host 127.0.0.1 --port 3000
```

For API-only integrations, `app.main:app` is still available. Opening
`frontend/index.html` directly or serving it with `http.server` does not provide
the analysis API.

Choose rules and komi before manual analysis. For SGF uploads, these controls
fill missing metadata only; existing recorded values take precedence.
Chinese rules select 7.5 komi; Japanese/Korean rules select 6.5; custom mode
allows an explicit scoring rule and komi.

Use **导入 SGF** to select and immediately preview a file, or place moves and use **停一手 / 悔棋** for
manual entry. **预览分析 -> 确认并分析** submits the accepted record. The report
panel shows completed positions and a cancel button. Refresh can restore the
current task while it remains in server memory; clearing/editing input prevents
late results from replacing the new board. Only a task ID is retained in the
browser, not the game itself. Re-import after server restart or expiry.

Defaults: **one running job, two waiting, 900-second deadline, 30-minute result
retention**, with additional count/size caps. Run one application worker only.
These settings and optional remote HTTPS API configuration are documented in
[the job contract](docs/JOB_CONTRACT.md). CORS is not authentication; public
hosting and abuse protection are still M5 work.

The review board uses red square **!** markers for evaluated mistakes, gray
squares for other played moves, green triangles for recommendations and blue
numbered circles for other candidates. When actual and recommended points
coincide, one green **=** marker replaces overlapping symbols. Candidate numbers
match the report. Coordinates, a text equivalent, optional move numbers and a
candidate visibility toggle remain available at mobile sizes. Analysis opens
the highest-ranked mistake; use **Continue entry / 继续录入** to edit the game again.
See [local workspace acceptance](docs/LOCAL_WORKSPACE_ACCEPTANCE.md) for the
startup, real-engine and responsive-browser checks.

### M5 Deployment Candidate

The production candidate serves the frontend and API from one HTTPS origin,
starts only after real KataGo readiness succeeds, runs one non-root Uvicorn
worker, keeps jobs/results in bounded ephemeral memory, and disables request,
engine and access logs that could contain private game data. Expensive requests
are limited per client and globally; exact Host validation, strict security
headers and Pages-only CORS are enabled only in `app.production`.

The proposed first host is one always-on Fly.io Sydney `shared-cpu-2x` Machine
with 2 GiB RAM and no database/volume. Current estimated compute is about
US$18.40/month; authorization is required before provisioning, with a proposed
US$25/month project ceiling. Fly does not provide a provider-enforced billing
cap or alert. Full commands, artifact hashes, licenses, limits and rollback are
in the [M5 deployment runbook](docs/M5_DEPLOYMENT.md); current evidence and
pending gates are in [M5 acceptance](docs/M5_ACCEPTANCE.md).

### Current API

| Endpoint | Input / behavior |
| --- | --- |
| `GET /health` | HTTP liveness only; does not check KataGo readiness |
| `GET /ready` | Fresh real model-load/version check; expensive, not a frequent polling endpoint |
| `POST /api/v1/parse-sgf` | Validated upload preview, no engine; identifies missing metadata |
| `POST /api/v1/validate-moves` | Equivalent preview for manual game JSON, no engine |
| `POST /api/v1/replay-moves` | Same preview plus server-generated snapshots, used for manual placement/pass |
| `POST /api/v1/jobs` | Confirmed canonical input -> HTTP 202, job schema 1.0 and opaque ID |
| `GET /api/v1/jobs/{id}` | State, progress and report; 404 after expiry/restart |
| `GET /api/v1/jobs/{id}/input` | Stable input snapshot for refresh recovery |
| `DELETE /api/v1/jobs/{id}` | Cancel queued or running analysis |
| `POST /api/v1/analyze-sgf` | Multipart `file`; `rules`, `komi`, `loss_threshold`, `severe_threshold` and `limit` are query parameters |
| `POST /api/v1/analyze-moves` | Explicit rules/komi and `{color, sgf}` moves; explicit `null` represents pass |

```bash
curl --fail-with-body \
  'http://127.0.0.1:3000/api/v1/analyze-sgf?loss_threshold=3.0&limit=5' \
  -F 'file=@samples/sample_game.sgf'

curl --fail-with-body 'http://127.0.0.1:3000/api/v1/analyze-moves' \
  -H 'Content-Type: application/json' \
  -d '{"board_size":19,"rules":"japanese","komi":6.5,"moves":[{"color":"B","sgf":"pd"},{"color":"W","sgf":"dd"}],"loss_threshold":3.0,"limit":5}'
```

The examples above are compatibility endpoints and share the bounded queue.
The browser uses jobs. Reports use schema `3.0`; that number is a data format version,
not a claim that product v3 or v1 is complete. Defaults are `loss_threshold=3`,
`severe_threshold=5`, `limit=5`; limit is 1-5, thresholds are finite and severe
must be >= obvious. A short sample may have no qualifying mistakes. Use
`samples/m3_mistake.sgf` for a synthetic obvious-mistake example.
Missing fields in otherwise successful engine responses produce HTTP 200 with
`status=partial`, explicit coverage and null values, not a fabricated clean game.
Protocol/startup failures still return 503. Old heuristic report fields were
removed; update backend and frontend together. See [report contract](docs/REPORT_CONTRACT.md).
Preview schema is `1.0`. See [the input contract](docs/INPUT_CONTRACT.md) for
limits, supported SGF properties, error responses and pass semantics.
See [the engine contract](docs/ENGINE_CONTRACT.md) for score perspectives,
candidate PVs, provenance and missing-evidence behavior.

## Current Status

Updated: **2026-08-29**. M5 development branch: `codex/m5-deployment`.

| Area | Status and limitation |
| --- | --- |
| SGF input | Shared replay validation, strict limits, metadata confirmation and explicit variation warnings; unsupported setups/rules fail |
| Manual entry | Shared server-side replay validation, placement/pass/undo/clear, names and metadata confirmation |
| KataGo | Real model readiness, process reuse, strict JSONL matching, explicit played-move search, genuine PVs and fixed-black evidence |
| Mistakes / report | Configurable 3/5-point thresholds, top-five summary plus all chronological markers, coverage and quality notes; no heuristic teaching |
| Web service | Same-origin local UI/API, on-demand macOS start/stop, bounded jobs, cancellation, progress and refresh recovery |
| Verification | 309 Python tests including live KataGo cases and 40 frontend tests; local real-engine, Pages and deployment contracts pass |
| Deployment | Pinned candidate and runbook prepared; Pages is a read-only showcase and paid/public analysis is deferred |

The [Pages showcase](https://yulinhenryou.github.io/go-review-ai/) publishes the
current review UI with a checked-in, sanitized report generated by real KataGo.
It is deliberately read-only: GitHub Pages cannot run Python or KataGo, so uploads
and new analysis still run only in the local workspace.

`gh-pages` is a separate publication branch and is **not automatically updated**
by pushing `main`. Build it with `python scripts/build_pages.py`, verify the output,
then publish that generated tree to `gh-pages`.
See the [detailed status audit](docs/PROJECT_STATUS.md) for evidence and limitations.

## Roadmap

| Milestone | Deliverable | Gate |
| --- | --- | --- |
| M0 | Repository inventory, archive index, README and v1 plan | Complete; housekeeping and archive tag uploaded |
| M1 | Shared validated game model and supported input contract | Complete; 173 tests reverified and main/branch uploaded at d08fc47 |
| M2 | Reliable, efficient real KataGo analysis | Implemented and verified with real models; see acceptance evidence and remaining limits |
| M3 | Obvious-mistake selection and concise factual report | Implemented and reverified; [acceptance](docs/M3_ACCEPTANCE.md) records coverage, live evidence and browser smoke |
| M4 | Complete browser flow with bounded analysis jobs | Implemented and verified locally; [acceptance](docs/M4_ACCEPTANCE.md) |
| M5 | Deployable web release and real-engine acceptance | Local candidate and static showcase pass; paid host/Linux/public second-device gates are deferred |

The active product mode is local analysis plus a static Pages showcase. M5 remains
open until a public backend and different-network acceptance are intentionally resumed.
GitHub terminal write access was restored and verified on 2026-08-27. Keep
[the access recovery guide](docs/GITHUB_AUTH.md) for future credential renewal.

## Development and Archives

- Keep parsing, engine integration, analysis, classification and rendering separate.
- Make one focused change per branch/PR; include relevant tests and verification.
- Keep `main` runnable. Use `codex/` branches for Codex implementation work.
- Do not import from `archive/`, load archived reports as defaults, or publish it.
- Keep runtime logs, private uploads, local configuration and model weights out of Git.
- Preserve historical work through tags and commits; do not rewrite shared history.

The [archive index](archive/README.md) records retained output and retired module
history. Old build caches can retain removed Python files; use a fresh build
directory when packaging and inspect the wheel for retired modules.
