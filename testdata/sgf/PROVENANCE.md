# SGF corpus provenance

Public Go game records used by `crates/weiqi-core/tests/sgf_extract.rs`. Every
file here may be published. A record's stored result, commentary and
variations are test data, never analysis evidence. Private SGFs never go here.

| File | SHA-256 | Source | Changes |
| --- | --- | --- | --- |
| `kejie-2025-11-27.sgf` | `a79b780a…c8521db` | Prototype `legacy/samples/test_game_kejie.sgf` | None (byte-identical copy) |
| `kejie-2025-11-27-gbk.sgf` | `4ba3419e…4067d5f` | Derived from `kejie-2025-11-27.sgf` | `GN` repaired, `CA` removed, GBK-encoded (below) |
| `maruyama-ito-1976.sgf` | `9b4ed82c…bd738ba` | Prototype `legacy/samples/benchmark_pro_game.sgf` | None (byte-identical copy) |

Full hashes: `shasum -a 256 testdata/sgf/*.sgf`.

## `kejie-2025-11-27.sgf`

Ke Jie (Black) vs Wang Zejin (White), 2025-11-27, round 11 of the 27th China
Weiqi League (per its `GN`), Chinese rules, komi 7.5, `RE[黑胜白]`. It has 1212
nodes: a 111-move main line and 110 commentary variations. Its `GN` says
"绝艺讲解" (Fine Art commentary). The owner approved publishing Ke Jie's games
for this project on 2026-11-03 (MIGRATION D06). The upstream source was not recorded when the prototype
added the file, so it is unknown.

The file shows two real-world irregularities: `GN` is double-encoded (UTF-8
bytes read as Latin-1 and encoded again as UTF-8), and `RE` is a Chinese
phrase rather than SGF form. Both are kept as found.

## `kejie-2025-11-27-gbk.sgf`

This is a stand-in for Chinese server exports in GBK without `CA`. It is not
a genuine export. It was made from the UTF-8 file with Python 3:

1. `GN` is repaired by reversing the double encoding
   (`value.encode("latin-1").decode("utf-8")`), giving
   `第27届中国围甲联赛第11轮 深圳龙华VS河南丰博<绝艺讲解>`.
2. The first `CA[UTF-8]` is removed.
3. The text is encoded with Python's `gbk` codec.

A genuine GBK export, with its provenance, should replace or join it when one
is available.

## `maruyama-ito-1976.sgf`

Maruyama Toyoji (Black) vs Ito Yoji (White), 1976-01-28, 1st Kisei, 235 moves,
komi 5.5, `RE[W+6.5]`. It originates from
[Sabaki's `test/sgf/pro_game.sgf`](https://github.com/SabakiHQ/Sabaki/blob/d451324de9353cbb96ccee0cd3b6e6137a48dfaa/test/sgf/pro_game.sgf)
(Sabaki's repository is MIT-licensed, checked 2026-11-04). The prototype
normalised it with sgfmill for its M2 benchmark, adding `SZ[19]`,
`RU[Japanese]`, `FF[4]` and `CA[UTF-8]`; the moves and komi are as upstream. `RU[Japanese]` is the prototype's benchmark choice,
not a verified historical rule. The file has no `GM`.
