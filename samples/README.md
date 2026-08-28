# Sample Inputs

| File | Purpose | Limitations |
| --- | --- | --- |
| `sample_game.sgf` | Small regression input used by the CLI and tests; four moves on the first variation | Synthetic example, not a benchmark or proof of KataGo accuracy; M1 explicitly sets Japanese rules |
| `m3_mistake.sgf` | Six-move synthetic game created for M3, with intentionally costly black edge moves | Public test input, not a human game or strength benchmark; real engine observations in `docs/evidence/m3-report.json` |
| `test_game_kejie.sgf` | Existing optional manual SGF with variations and Chinese rules metadata | Not used by the test suite; source/provenance not recorded here, some metadata appears misdecoded, not a release acceptance fixture |
| `benchmark_pro_game.sgf` | 235-move public game for M2 performance measurement | Metadata normalized as described below; not a ground-truth mistake-label dataset |

Do not change an input used by tests without reviewing the affected assertions.
An SGF's stored game result or commentary is not analysis evidence.
M1 added only `RU[Japanese]` to the synthetic sample; its moves and existing
metadata were retained and their assertions checked. Missing-rule cases now
have dedicated tests rather than depending on an implicit sample default.

## Long Benchmark Provenance

Source: [Sabaki's public pro_game.sgf fixture](https://github.com/SabakiHQ/Sabaki/blob/d451324de9353cbb96ccee0cd3b6e6137a48dfaa/test/sgf/pro_game.sgf).
It records Maruyama Toyoji vs Ito Yoji, dated 1976-01-28, with 235 moves and 5.5
komi. The upstream file omits board size and rules. For this benchmark only,
sgfmill serialization added explicit SZ[19], RU[Japanese], FF[4] and CA[UTF-8];
the move sequence and recorded komi were retained. Japanese rules are the chosen
benchmark assumption, not a verified historical adjudication. This normalization
does not relax the application's missing-metadata validation.

Historical generated reports were moved to [the archive](../archive/README.md).
Future generated reports belong in the ignored `reports/` directory. Private
uploaded SGFs belong in the ignored `uploads/` directory, not in this folder.
