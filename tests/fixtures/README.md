# Engine Fixtures

`jsonl_engine.py` is a subprocess test double for protocol and cleanup failures.
It is never an application engine.

`katago_real_short.json` was captured on 2026-08-27 with the real installed
KataGo 1.16.4 Metal backend and the Homebrew-bundled model
`kata1-b18c384nbt-s9996604416-d4316597426.bin.gz` (SHA-256 is inside the fixture).
Input: the repository's synthetic four-move `samples/sample_game.sgf`.
Search: 32 visits, `config/analysis.cfg`, fixed BLACK raw perspective.

The fixture contains actual queries, complete responses and normalized results.
The loaded-model `name` was reduced to its basename; no local absolute paths,
private uploads, credentials or stderr are stored. Timing is an observation,
not a deterministic test assertion. `test_recorded_engine.py` remaps request IDs
and replays the responses to verify every normalized field except elapsed time
and generated IDs. Exact equality is for fixture transformations, not live search.

Regenerate only deliberately with a public/synthetic input:

```bash
python -m scripts.benchmark_engine samples/sample_game.sgf --visits 32 \
  --record-public-fixture --output tests/fixtures/katago_real_short.json
```

The script requires the documented engine environment. Never use the recording
flag for private SGFs. Model weights are external and are not redistributed here.
