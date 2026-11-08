# Recorded engine exchanges

Real KataGo exchanges kept as deterministic test fixtures (ARCHITECTURE §5.4,
MIGRATION E09). They are replayed by `python/tests/engine/test_recorded.py`.
A replay proves that our code still reads what KataGo really sent; it proves
nothing about live search, which `python/tests/live/` checks.

## `short-game.json`

- **Input:** `testdata/sgf/synthetic-short.sgf` (synthetic, see
  `../sgf/PROVENANCE.md`): six moves ending in two passes, Japanese rules,
  komi 6.5, every turn 0–6 analysed with ownership.
- **Engine:** KataGo 1.16.4 (Homebrew build, Metal backend), model
  `kata1-b18c384nbt-s9996604416-d4316597426` (SHA-256 in the fixture),
  `config/katago/analysis.cfg`, 32 visits, PV length 8, overrides forced by
  `KataGoEngine` (values in BLACK perspective, logging off).
- **Recorded:** 2026-11-08 on the owner's Mac (Apple M4, macOS; the exact
  values are in the fixture's `recorded` field).
- **Contents:** the input, the engine identity, every message sent and
  received in order, and each turn's normalised result and `query_key`.
  Query ids are renumbered and the model's file name keeps no directory; no
  local path, private game, credential or engine log is stored. Model
  weights are not redistributed.

Regenerate only on purpose, from `python/`, with a public record:

```bash
KATAGO_MODEL_PATH=/path/to/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz \
  uv run python -m weiqi.tools.record_engine ../testdata/sgf/synthetic-short.sgf \
  --visits 32 --ownership --output ../testdata/engine/short-game.json
```

The tool refuses records outside `testdata/sgf/` or not listed in its
`PROVENANCE.md`. Search is not deterministic, so a new recording replaces
the stored values; commit it on its own so the change can be reviewed.
