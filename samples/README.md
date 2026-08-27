# Sample Inputs

| File | Purpose | Limitations |
| --- | --- | --- |
| `sample_game.sgf` | Small regression input used by the CLI and tests; four moves on the first variation | Synthetic example, not a benchmark or proof of KataGo accuracy; no rules property |
| `test_game_kejie.sgf` | Existing optional manual SGF with variations and Chinese rules metadata | Not used by the test suite; source/provenance not recorded here, some metadata appears misdecoded, not a release acceptance fixture |

Do not change an input used by tests without reviewing the affected assertions.
An SGF's stored game result or commentary is not analysis evidence.

Historical generated reports were moved to [the archive](../archive/README.md).
Future generated reports belong in the ignored `reports/` directory. Private
uploaded SGFs belong in the ignored `uploads/` directory, not in this folder.
