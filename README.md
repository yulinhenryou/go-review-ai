# go-review-ai

A CLI MVP for analyzing Go SGF files with KataGo and generating human-readable review reports.

## Goal

Input one SGF file, analyze it with KataGo, find key mistakes, and generate a plain-text review report.

## Phase 1

- CLI only
- one SGF file at a time
- plain-text output
- no web frontend
- no database

## Files

- src/sgf_parser.py
- src/katago_client.py
- src/analyzer.py
- src/classifier.py
- src/report_writer.py
- src/main.py

## KataGo Setup

The real engine client is `KataGoClient` in `src/katago_client.py`.
It uses KataGo `analysis` mode via `subprocess`.

1. Install KataGo on your machine and ensure the `katago` binary is on your `PATH`.
2. Download a KataGo model file (for example, `*.bin.gz`).
3. Ensure you have a KataGo analysis config file (for example, `analysis_example.cfg`).
4. Export these environment variables:

```bash
export KATAGO_MODEL_PATH="/absolute/path/to/model.bin.gz"
export KATAGO_CONFIG_PATH="/absolute/path/to/analysis.cfg"
```

Optional:

```bash
export KATAGO_PATH="katago"
```

If KataGo is unavailable, `src/main.py` prints a clear message and falls back to `MockEngineClient` so local tests remain runnable.

## Usage

Run the sample pipeline:

```bash
python -m src.main
```

- With `KATAGO_MODEL_PATH` and `KATAGO_CONFIG_PATH` set, this uses real KataGo.
- Without them, it falls back to the deterministic mock engine.

## API (Minimal FastAPI Backend)

This project now includes a minimal FastAPI app that exposes SGF analysis as JSON for future frontend use.

Install API dependencies:

```bash
pip install fastapi uvicorn python-multipart httpx
```

Run the API locally:

```bash
uvicorn app.main:app --reload
```

Analyze an SGF upload:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/analyze-sgf" \
  -F "file=@samples/sample_game.sgf" \
  -F "loss_threshold=1.0" \
  -F "limit=3"
```

Analyze a position/game state from JSON moves:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/analyze-moves" \
  -H "Content-Type: application/json" \
  -d '{
    "board_size": 19,
    "komi": 6.5,
    "players": {
      "black": "Lee Sedol",
      "white": "AlphaGo"
    },
    "moves": [
      {"color": "B", "sgf": "pd"},
      {"color": "W", "sgf": "dd"},
      {"color": "B", "sgf": "qp"},
      {"color": "W", "sgf": "dc"}
    ],
    "loss_threshold": 1.0,
    "limit": 3
  }'
```

Health check:

```bash
curl "http://127.0.0.1:8000/health"
```

## Manual Verification (Real Engine)

Use this command to verify one sample SGF against the real engine client:

```bash
python -c "from src.main import build_review_report_for_sgf; from src.katago_client import KataGoClient; print(build_review_report_for_sgf('samples/sample_game.sgf', KataGoClient.from_environment(), loss_threshold=1.0, limit=3))"
```

Expected result: a report with `Game Summary`, `Top Mistakes`, and `Mistake Explanations`, generated from KataGo output.

## Tests

Automated tests do not require a local KataGo installation.
They use `MockEngineClient` and subprocess mocking for real-client parsing/error paths.

API tests are included and will run when FastAPI dependencies are installed.
