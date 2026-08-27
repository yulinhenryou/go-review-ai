# go-review-ai

A Go game review prototype built around KataGo. The first release is intended to
turn an uploaded SGF or a manually entered game into a short, evidence-based web
report highlighting obvious mistakes.

**Current status: early prototype, not a validated v1 release.** The existing UI
and API demonstrate the flow, but engine correctness, input validation, and
end-to-end deployment still need work. See [Current Status](#current-status).

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
| Game input | Custom SGF parser and JSON move models |
| Analysis | External KataGo binary, model, and analysis config; JSON over subprocess stdin/stdout |
| API | FastAPI, Pydantic, Uvicorn, python-multipart |
| Frontend | HTML, CSS, vanilla JavaScript, Canvas 2D |
| Tests | pytest, HTTPX / FastAPI TestClient, mocked engine responses |
| Static preview | GitHub Pages, published from `gh-pages` |

KataGo models and executables are not bundled. There is no deployed Python backend
in this repository's Pages site. Mature SGF/rules libraries will be evaluated in
the input milestone; they are not current dependencies.

## How It Works

```text
SGF upload -----------------> SGF parser ----+
                                            |
Manual board -> JSON moves -> API models ----+-> ParsedGame
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

The CLI and API share the review functions in `src/main.py`. The current pipeline
also runs experimental classification and teaching heuristics. V1 will remove
unsupported teaching claims from the default report, preserving the old prototype
in the [archive](archive/README.md).

### Repository Layout

| Path | Responsibility |
| --- | --- |
| `src/sgf_parser.py` | SGF parsing and parsed game records |
| `src/katago_client.py` | Engine protocol, real client, current mock implementation |
| `src/analyzer.py` | Position-by-position analysis orchestration |
| `src/mistake_selector.py`, `src/mistake_severity.py` | Mistake ranking and severity |
| `src/classifier.py`, `src/key_points.py` | Experimental heuristics, still called by the prototype |
| `src/review_result.py` | Structured result contract and serialization |
| `src/report_writer.py`, `src/chinese_explanations.py`, `src/user_facing_labels.py` | Report templates and labels |
| `src/main.py` | Shared review pipeline and sample CLI entry |
| `app/` | FastAPI routes and request models |
| `frontend/` | Current browser prototype and Pages publication source |
| `tests/` | Active regression tests |
| `samples/` | Sample SGF inputs; see [sample notes](samples/README.md) |
| `docs/` | Status audit and proposed v1 development path |
| `archive/` | Historical output snapshots and prototype archive index; not runtime code |

### Run the Current Prototype

Run commands from the repository root. For a fresh environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install fastapi uvicorn python-multipart httpx pytest
python -m pytest -q -ra
```

These are the current direct dependency installation steps. Reproducible package
installation and dependency locking are part of milestone M1; an isolated clean
installation has not been verified in this audit.

Run the sample CLI:

```bash
python -m src.main
```

**Demo-data warning:** without `KATAGO_MODEL_PATH` and `KATAGO_CONFIG_PATH`, the
default engine factory falls back to deterministic mock data. The API does not
currently identify that fallback in its result. Do not treat those reports as
KataGo evaluations. V1 must fail clearly when the real engine is unavailable.

For the real engine, install KataGo and obtain a compatible model and analysis
config following the [KataGo project](https://github.com/lightvector/KataGo).
Set the environment before starting the CLI or backend:

```bash
export KATAGO_PATH="katago"
export KATAGO_MODEL_PATH="/absolute/path/to/model.bin.gz"
export KATAGO_CONFIG_PATH="/absolute/path/to/analysis.cfg"
```

These placeholders must be replaced with real local files. Setting them alone
does not validate the engine or its output. Runtime engine failures currently
raise errors; the configuration fallback is not a general recovery mechanism.

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

### Current API

| Endpoint | Input / behavior |
| --- | --- |
| `GET /health` | HTTP liveness only; does not check KataGo readiness |
| `POST /api/v1/analyze-sgf` | Multipart `file`; `loss_threshold` and `limit` are query parameters |
| `POST /api/v1/analyze-moves` | JSON game metadata and a list of `{color, sgf}` moves; `null` represents pass |

```bash
curl --fail-with-body \
  'http://127.0.0.1:8000/api/v1/analyze-sgf?loss_threshold=3.0&limit=5' \
  -F 'file=@samples/sample_game.sgf'

curl --fail-with-body 'http://127.0.0.1:8000/api/v1/analyze-moves' \
  -H 'Content-Type: application/json' \
  -d '{"board_size":19,"komi":6.5,"moves":[{"color":"B","sgf":"pd"},{"color":"W","sgf":"dd"}],"loss_threshold":3.0,"limit":5}'
```

The existing API returns review schema `2.0`; that number is a data format version,
not a claim that product v2 or v1 is complete. A short sample may have no results
above the example threshold. The proposed v1 threshold is not yet the default.

## Current Status

Audit date: **2026-08-27**, prototype baseline: `7447f54`.

| Area | Status and limitation |
| --- | --- |
| SGF input | Main-line parser exists; rules/setup properties and legality are not adequately handled |
| Manual entry | 19x19 placement, captures, undo and navigation exist; rule coverage, pass control and metadata editing remain incomplete |
| KataGo | Adapter exists; missing played-move values and missing PVs can be fabricated; score perspective is not enforced |
| Mistakes / report | Ranking and templates exist; heuristic labels and fallback values are not sufficient evidence of Go causes |
| Web service | Upload and JSON endpoints exist; work blocks requests and there are no bounded analysis jobs or readiness checks |
| Verification | Existing local suite: **54 passed**, including API tests; no real-engine or browser interaction acceptance run in this audit |
| Deployment | Pages serves the frontend, not a complete online analysis service |

The [Pages preview](https://yulinhenryou.github.io/go-review-ai/) was checked against
the local HTML during this audit and matched byte-for-byte. This checks publication,
not browser behavior. It still targets the visitor's loopback address, and the
Pages origin is absent from the backend's CORS allowlist. Starting a backend on the
developer's computer does not make analysis available to other visitors.

`gh-pages` is a separate publication branch and is **not automatically updated**
by pushing `main`. This housekeeping pass leaves the deployed prototype unchanged.
See the [detailed status audit](docs/PROJECT_STATUS.md) for evidence and limitations.

## Roadmap

| Milestone | Deliverable | Gate |
| --- | --- | --- |
| M0 | Repository inventory, archive index, README and v1 plan | This housekeeping pass; functional plan awaits approval |
| M1 | Shared validated game model and supported input contract | SGF and equivalent manual moves produce the same legal game |
| M2 | Reliable, efficient real KataGo analysis | Every reported evaluation is traceable; no invented scores or variations |
| M3 | Obvious-mistake selection and concise factual report | Stable threshold/ranking tests and zero unsupported teaching claims |
| M4 | Complete browser flow with bounded analysis jobs | Upload and manual-entry workflows pass browser acceptance tests |
| M5 | Deployable web release and real-engine acceptance | A second device completes a real game review against the deployed backend |

Read [the v1 development path and acceptance criteria](docs/ROADMAP.md) before
starting M1. Functional development has not begun in this housekeeping pass.

## Development and Archives

- Keep parsing, engine integration, analysis, classification and rendering separate.
- Make one focused change per branch/PR; include relevant tests and verification.
- Keep `main` runnable. Use `codex/` branches for Codex implementation work.
- Do not import from `archive/`, load archived reports as defaults, or publish it.
- Keep runtime logs, private uploads, local configuration and model weights out of Git.
- Preserve historical work through tags and commits; do not rewrite shared history.

The [archive index](archive/README.md) records what was moved, why it was moved,
and which still-active modules need deliberate replacement during v1 development.
